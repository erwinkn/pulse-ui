"""
Command-line interface for Pulse UI.
This module provides the CLI commands for running the server and generating routes.
"""
# typer relies on function calls used as default values
# pyright: reportCallInDefaultInitializer=false

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Callable, cast

import typer

from pulse.cli.dependencies import (
	DependencyError,
	DependencyPlan,
	DependencyResolutionError,
	check_web_dependencies,
	prepare_web_dependencies,
)
from pulse.cli.folder_lock import FolderLock
from pulse.cli.helpers import load_app_from_target
from pulse.cli.logging import CLILogger
from pulse.cli.models import AppLoadResult, CommandSpec
from pulse.cli.processes import execute_commands
from pulse.cli.secrets import resolve_dev_secret
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import (
	ENV_PULSE_BUN_RENDER_SERVER_ADDRESS,
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
	ENV_PULSE_REACT_SERVER_ADDRESS,
	ENV_PULSE_SECRET,
	PulseEnv,
	env,
)
from pulse.helpers import find_available_port
from pulse.version import __version__ as PULSE_PY_VERSION

cli = typer.Typer(
	name="pulse",
	help="Pulse UI - Python to TypeScript bridge with server-side callbacks",
	no_args_is_help=True,
)


@cli.command(
	"run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def run(
	ctx: typer.Context,
	app_file: str = typer.Argument(
		...,
		help=("App target: 'path/to/app.py[:var]' (default :app) or 'module.path:var'"),
	),
	address: str = typer.Option(
		"localhost",
		"--address",
		help="Host uvicorn binds to",
	),
	port: int = typer.Option(8000, "--port", help="Port uvicorn binds to"),
	# Env flags
	dev: bool = typer.Option(False, "--dev", help="Run in development mode"),
	prod: bool = typer.Option(False, "--prod", help="Run in production mode"),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
	server_only: bool = typer.Option(False, "--server-only", "--backend-only"),
	web_only: bool = typer.Option(False, "--web-only"),
	react_server_address: str | None = typer.Option(
		None,
		"--react-server-address",
		help="Full URL of React server (required for single-server + --server-only)",
	),
	reload: bool | None = typer.Option(None, "--reload/--no-reload"),
	find_port: bool = typer.Option(True, "--find-port/--no-find-port"),
	verbose: bool = typer.Option(
		False, "--verbose", help="Show all logs without filtering"
	),
):
	"""Run the Pulse server and web development server together."""
	extra_flags = list(ctx.args)

	# Validate mode flags (dev is default if neither specified)
	if dev and prod:
		logger = CLILogger("dev", plain=plain)
		logger.error("Please specify only one of --dev or --prod.")
		raise typer.Exit(1)

	# Set mode: prod if specified, otherwise dev (default)
	mode: PulseEnv = "prod" if prod else "dev"
	env.pulse_env = mode
	logger = CLILogger(mode, plain=plain)

	# Turn on reload in dev only
	if reload is None:
		reload = env.pulse_env == "dev"

	if server_only and web_only:
		logger.error("Cannot use --server-only and --web-only at the same time.")
		raise typer.Exit(1)

	if find_port:
		port = find_available_port(port)

	logger.print(f"Loading app from {app_file}")
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	is_single_server = app_instance.mode == "single-server"
	if is_single_server:
		logger.print("Single-server mode")

	# In single-server + server-only mode, require explicit React server address
	if is_single_server and server_only:
		if not react_server_address:
			logger.error(
				"--react-server-address is required when using single-server mode with --server-only."
			)
			raise typer.Exit(1)
		os.environ[ENV_PULSE_REACT_SERVER_ADDRESS] = react_server_address

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists() and not server_only:
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	dev_secret: str | None = None
	if app_instance.env != "prod":
		dev_secret = os.environ.get(ENV_PULSE_SECRET) or resolve_dev_secret(
			web_root if web_root.exists() else app_ctx.app_file
		)

	if env.pulse_env == "dev" and not server_only:
		try:
			to_add = check_web_dependencies(
				web_root,
				pulse_version=PULSE_PY_VERSION,
			)
		except DependencyResolutionError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
		except DependencyError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None

		if to_add:
			try:
				dep_plan = prepare_web_dependencies(
					web_root,
					pulse_version=PULSE_PY_VERSION,
				)
				if dep_plan:
					_run_dependency_plan(logger, web_root, dep_plan)
			except subprocess.CalledProcessError:
				logger.error("Failed to install web dependencies with Bun.")
				raise typer.Exit(1) from None

	server_args = extra_flags if not web_only else []
	web_args = extra_flags if web_only else []

	commands: list[CommandSpec] = []

	# Track readiness for announcement
	server_ready = {"server": False, "web": False}
	announced = False

	def mark_web_ready() -> None:
		server_ready["web"] = True
		check_and_announce()

	def mark_server_ready() -> None:
		server_ready["server"] = True
		check_and_announce()

	def check_and_announce() -> None:
		"""Announce when all required servers are ready."""
		nonlocal announced
		if announced:
			return

		needs_server = not web_only
		needs_web = not server_only

		if needs_server and not server_ready["server"]:
			return
		if needs_web and not server_ready["web"]:
			return

		# All required servers are ready, show announcement
		announced = True
		protocol = "http" if address in ("127.0.0.1", "localhost") else "https"
		server_url = f"{protocol}://{address}:{port}"
		logger.write_ready_announcement(address, port, server_url)

	# Build web command first (when needed) so we can set PULSE_REACT_SERVER_ADDRESS
	# before building the uvicorn command, which needs that env var
	if not server_only:
		web_port = find_available_port(5173)
		web_cmd = build_web_command(
			web_root=web_root,
			extra_args=web_args,
			port=web_port,
			mode=app_instance.env,
			ready_pattern=r"localhost:\d+",
			on_ready=mark_web_ready,
		)
		commands.append(web_cmd)
		# Set env var so app can read the React server address (only used in single-server mode)
		env.react_server_address = f"http://localhost:{web_port}"

	if not web_only:
		server_cmd = build_uvicorn_command(
			app_ctx=app_ctx,
			address=address,
			port=port,
			reload_enabled=reload,
			extra_args=server_args,
			dev_secret=dev_secret,
			server_only=server_only,
			web_root=web_root,
			verbose=verbose,
			ready_pattern=r"Application startup complete",
			on_ready=mark_server_ready,
		)
		commands.append(server_cmd)

	with FolderLock(web_root):
		try:
			exit_code = execute_commands(
				commands,
				tag_mode=logger.get_tag_mode(),
			)
			raise typer.Exit(exit_code)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None


@cli.command("dev")
def dev(
	app_file: str = typer.Argument(
		...,
		help=("App target: 'path/to/app.py[:var]' (default :app) or 'module.path:var'"),
	),
	address: str = typer.Option(
		"localhost",
		"--address",
		help="Host to bind to",
	),
	port: int = typer.Option(8000, "--port", help="Port to bind to"),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
):
	"""Run the Pulse development server."""
	env.pulse_env = "dev"
	logger = CLILogger("dev", plain=plain)

	logger.print(f"Loading app from {app_file}")
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists():
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	dev_secret: str | None = None
	if app_instance.env != "prod":
		dev_secret = os.environ.get(ENV_PULSE_SECRET) or resolve_dev_secret(
			web_root if web_root.exists() else app_ctx.app_file
		)

	# Check web dependencies
	try:
		to_add = check_web_dependencies(
			web_root,
			pulse_version=PULSE_PY_VERSION,
		)
	except DependencyResolutionError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None
	except DependencyError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None

	if to_add:
		try:
			dep_plan = prepare_web_dependencies(
				web_root,
				pulse_version=PULSE_PY_VERSION,
			)
			if dep_plan:
				_run_dependency_plan(logger, web_root, dep_plan)
		except subprocess.CalledProcessError:
			logger.error("Failed to install web dependencies with Bun.")
			raise typer.Exit(1) from None

	# Run codegen before starting servers
	try:
		logger.print("Generating routes...")
		app_instance.run_codegen(
			f"http://{address}:{port}",
			f"http://{address}:{port}",
		)
		logger.success("Routes generated")
	except Exception as exc:
		logger.error(f"Failed to generate routes: {exc}")
		raise typer.Exit(1) from None

	# Track readiness for announcement
	server_ready = {"server": False, "vite": False, "bun": False}
	announced = False

	def mark_server_ready() -> None:
		server_ready["server"] = True
		check_and_announce()

	def mark_vite_ready() -> None:
		server_ready["vite"] = True
		check_and_announce()

	def mark_bun_ready() -> None:
		server_ready["bun"] = True
		check_and_announce()

	def check_and_announce() -> None:
		"""Announce when all required servers are ready."""
		nonlocal announced
		if announced:
			return

		if (
			not server_ready["server"]
			or not server_ready["vite"]
			or not server_ready["bun"]
		):
			return

		# All servers are ready, show announcement
		announced = True
		protocol = "http" if address in ("127.0.0.1", "localhost") else "https"
		server_url = f"{protocol}://{address}:{port}"
		logger.write_ready_announcement(address, port, server_url)

	# Build commands
	commands: list[CommandSpec] = []

	# Bun SSR server port (allocated first, before other servers)
	bun_port = find_available_port(3001)
	# Set React server address for Python app to use
	os.environ[ENV_PULSE_REACT_SERVER_ADDRESS] = f"http://{address}:{bun_port}"
	# Set Bun render server address for Python app to POST VDOM to
	os.environ[ENV_PULSE_BUN_RENDER_SERVER_ADDRESS] = f"http://{address}:{bun_port}"

	# Python server
	server_cmd = build_uvicorn_command(
		app_ctx=app_ctx,
		address=address,
		port=port,
		reload_enabled=True,
		extra_args=[],
		dev_secret=dev_secret,
		server_only=False,
		web_root=web_root,
		verbose=False,
		ready_pattern=r"Application startup complete",
		on_ready=mark_server_ready,
	)
	# Rename to "python" for output
	server_cmd = CommandSpec(
		name="python",
		args=server_cmd.args,
		cwd=server_cmd.cwd,
		env=server_cmd.env,
		ready_pattern=server_cmd.ready_pattern,
		on_ready=server_cmd.on_ready,
		on_spawn=server_cmd.on_spawn,
	)
	commands.append(server_cmd)

	# Vite dev server
	vite_port = find_available_port(5173)
	vite_cmd = build_web_command(
		web_root=web_root,
		extra_args=[],
		port=vite_port,
		mode="dev",
		ready_pattern=r"Local:.*http",
		on_ready=mark_vite_ready,
	)
	# Rename to "vite" for output
	vite_cmd = CommandSpec(
		name="vite",
		args=vite_cmd.args,
		cwd=vite_cmd.cwd,
		env=vite_cmd.env,
		ready_pattern=vite_cmd.ready_pattern,
		on_ready=vite_cmd.on_ready,
		on_spawn=vite_cmd.on_spawn,
	)
	commands.append(vite_cmd)

	# Bun SSR server
	bun_cmd = CommandSpec(
		name="bun",
		args=[
			"bun",
			"run",
			str(web_root / "src" / "server" / "server.ts"),
		],
		cwd=web_root,
		env=dict(
			os.environ,
			PORT=str(bun_port),
			FORCE_COLOR="1",
			PYTHONUNBUFFERED="1",
		),
		ready_pattern=r"Listening on",
		on_ready=mark_bun_ready,
	)
	commands.append(bun_cmd)

	with FolderLock(web_root):
		try:
			exit_code = execute_commands(
				commands,
				tag_mode=logger.get_tag_mode(),
			)
			raise typer.Exit(exit_code)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None


@cli.command("build")
def build(
	app_file: str = typer.Argument(
		...,
		help=("App target: 'path/to/app.py[:var]' (default :app) or 'module.path:var'"),
	),
	address: str = typer.Option(
		"localhost",
		"--address",
		help="Address for internal server during codegen",
	),
	port: int = typer.Option(
		8000, "--port", help="Port for internal server during codegen"
	),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
	no_check: bool = typer.Option(False, "--no-check", help="Skip type checking"),
	compile: bool = typer.Option(
		False, "--compile", help="Compile Bun SSR server to standalone executable"
	),
):
	"""Build Pulse app for production."""
	env.pulse_env = "prod"
	logger = CLILogger("prod", plain=plain)

	logger.print(f"Loading app from {app_file}")
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists():
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	# Check web dependencies
	try:
		to_add = check_web_dependencies(
			web_root,
			pulse_version=PULSE_PY_VERSION,
		)
	except DependencyResolutionError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None
	except DependencyError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None

	if to_add:
		try:
			dep_plan = prepare_web_dependencies(
				web_root,
				pulse_version=PULSE_PY_VERSION,
			)
			if dep_plan:
				_run_dependency_plan(logger, web_root, dep_plan)
		except subprocess.CalledProcessError:
			logger.error("Failed to install web dependencies with Bun.")
			raise typer.Exit(1) from None

	# Run codegen
	try:
		logger.print("Generating routes...")
		app_instance.run_codegen(
			f"http://{address}:{port}",
			f"http://{address}:{port}",
		)
		logger.success("Routes generated")
	except Exception as exc:
		logger.error(f"Failed to generate routes: {exc}")
		raise typer.Exit(1) from None

	# Run type checks
	if not no_check:
		logger.print("Checking types...")
		checks_passed = True

		# TypeScript type check
		try:
			result = subprocess.run(
				["bun", "run", "typecheck"],
				cwd=web_root,
				capture_output=True,
				text=True,
				timeout=60,
			)
			if result.returncode != 0:
				logger.error("TypeScript type check failed")
				logger.print(result.stderr or result.stdout)
				checks_passed = False
		except subprocess.TimeoutExpired:
			logger.error("TypeScript type check timed out")
			checks_passed = False
		except subprocess.CalledProcessError as exc:
			logger.error(f"TypeScript type check failed: {exc}")
			checks_passed = False

		# Python type check
		try:
			result = subprocess.run(
				[sys.executable, "-m", "basedpyright"],
				cwd=app_ctx.app_dir or Path.cwd(),
				capture_output=True,
				text=True,
				timeout=60,
			)
			if result.returncode != 0:
				logger.warning("Python type check failed (non-blocking)")
				logger.print(result.stderr or result.stdout)
		except subprocess.TimeoutExpired:
			logger.warning("Python type check timed out (non-blocking)")
		except Exception:
			logger.warning("Python type check skipped (non-blocking)")

		if not checks_passed:
			raise typer.Exit(1)
		logger.success("Type checks passed")

	# Run Vite production build
	try:
		logger.print("Building frontend...")
		result = subprocess.run(
			["bun", "run", "build"],
			cwd=web_root,
			capture_output=True,
			text=True,
			timeout=120,
		)
		if result.returncode != 0:
			logger.error("Frontend build failed")
			logger.print(result.stderr or result.stdout)
			raise typer.Exit(1)
		logger.success("Frontend build complete")
	except subprocess.TimeoutExpired:
		logger.error("Frontend build timed out")
		raise typer.Exit(1) from None
	except subprocess.CalledProcessError as exc:
		logger.error(f"Frontend build failed: {exc}")
		raise typer.Exit(1) from None

	# Verify build output exists
	dist_dir = web_root / "dist"
	if not dist_dir.exists():
		logger.error(f"Build artifacts not found at {dist_dir}")
		raise typer.Exit(1)

	# Compile Bun SSR server if requested
	if compile:
		_compile_bun_server(logger, web_root, app_instance.codegen.cfg.mode)

	logger.success(f"Build complete! Output: {dist_dir}")


@cli.command("start")
def start(
	app_file: str = typer.Argument(
		...,
		help=("App target: 'path/to/app.py[:var]' (default :app) or 'module.path:var'"),
	),
	address: str = typer.Option(
		"0.0.0.0",
		"--address",
		help="Host to bind to (default 0.0.0.0 for production)",
	),
	port: int = typer.Option(8000, "--port", help="Port to bind to"),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
	workers: int = typer.Option(
		1, "--workers", help="Number of Uvicorn worker processes"
	),
):
	"""Run the Pulse production server."""
	env.pulse_env = "prod"
	logger = CLILogger("prod", plain=plain)

	logger.print(f"Loading app from {app_file}")
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists():
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	# Check for build artifacts
	dist_dir = web_root / "dist"
	if not dist_dir.exists():
		msg = f"Build artifacts not found at {dist_dir}. Run 'pulse build' first to create production assets."
		logger.error(msg)
		raise typer.Exit(1)

	# Track readiness for announcement
	server_ready = {"server": False, "bun": False}
	announced = False

	def mark_server_ready() -> None:
		server_ready["server"] = True
		check_and_announce()

	def mark_bun_ready() -> None:
		server_ready["bun"] = True
		check_and_announce()

	def check_and_announce() -> None:
		"""Announce when all required servers are ready."""
		nonlocal announced
		if announced:
			return

		if not server_ready["server"] or not server_ready["bun"]:
			return

		# All servers are ready, show announcement
		announced = True
		protocol = "http" if address == "127.0.0.1" else "https"
		server_url = f"{protocol}://{address}:{port}"
		logger.write_ready_announcement(address, port, server_url)

	# Build commands
	commands: list[CommandSpec] = []

	# Bun SSR server port (allocated first, before other servers)
	bun_port = find_available_port(3001)
	# Set React server address for Python app to use
	os.environ[ENV_PULSE_REACT_SERVER_ADDRESS] = f"http://{address}:{bun_port}"
	# Set Bun render server address for Python app to POST VDOM to
	os.environ[ENV_PULSE_BUN_RENDER_SERVER_ADDRESS] = f"http://{address}:{bun_port}"

	# Python server (no reload in production)
	server_cmd = build_uvicorn_command(
		app_ctx=app_ctx,
		address=address,
		port=port,
		reload_enabled=False,
		extra_args=["--workers", str(workers)] if workers > 1 else [],
		dev_secret=None,
		server_only=False,
		web_root=web_root,
		verbose=False,
		ready_pattern=r"Application startup complete",
		on_ready=mark_server_ready,
	)
	# Rename to "python" for output
	server_cmd = CommandSpec(
		name="python",
		args=server_cmd.args,
		cwd=server_cmd.cwd,
		env=server_cmd.env,
		ready_pattern=server_cmd.ready_pattern,
		on_ready=server_cmd.on_ready,
		on_spawn=server_cmd.on_spawn,
	)
	commands.append(server_cmd)

	# Bun SSR server (use pre-built executable if available, otherwise run from source)
	executable_path = None
	if app_instance.codegen.cfg.mode == "managed":
		exe_candidate = (
			web_root.parent.parent
			/ "server"
			/ ("server.exe" if sys.platform == "win32" else "server")
		)
	else:
		exe_candidate = (
			web_root.parent
			/ "server"
			/ ("server.exe" if sys.platform == "win32" else "server")
		)

	if exe_candidate.exists():
		executable_path = exe_candidate
		bun_cmd = CommandSpec(
			name="bun",
			args=[str(executable_path)],
			cwd=web_root,
			env=dict(
				os.environ,
				PORT=str(bun_port),
				FORCE_COLOR="1",
				PYTHONUNBUFFERED="1",
			),
			ready_pattern=r"Listening on",
			on_ready=mark_bun_ready,
		)
	else:
		# Fall back to running from source with Bun
		bun_cmd = CommandSpec(
			name="bun",
			args=[
				"bun",
				"run",
				str(web_root / "src" / "server" / "server.ts"),
			],
			cwd=web_root,
			env=dict(
				os.environ,
				PORT=str(bun_port),
				FORCE_COLOR="1",
				PYTHONUNBUFFERED="1",
			),
			ready_pattern=r"Listening on",
			on_ready=mark_bun_ready,
		)
	commands.append(bun_cmd)

	with FolderLock(web_root):
		try:
			exit_code = execute_commands(
				commands,
				tag_mode=logger.get_tag_mode(),
			)
			raise typer.Exit(exit_code)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None


@cli.command("generate")
def generate(
	app_file: str = typer.Argument(
		..., help="App target: 'path.py[:var]' (default :app) or 'module:var'"
	),
	# Mode flags
	dev: bool = typer.Option(False, "--dev", help="Generate in development mode"),
	ci: bool = typer.Option(False, "--ci", help="Generate in CI mode"),
	prod: bool = typer.Option(False, "--prod", help="Generate in production mode"),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
):
	"""Generate TypeScript routes without starting the server."""
	# Validate mode flags
	mode_flags = [
		name for flag, name in [(dev, "dev"), (ci, "ci"), (prod, "prod")] if flag
	]
	if len(mode_flags) > 1:
		logger = CLILogger("dev", plain=plain)
		logger.error("Please specify only one of --dev, --ci, or --prod.")
		raise typer.Exit(1)

	# Set mode: use specified mode, otherwise dev (default)
	mode: PulseEnv = cast(PulseEnv, mode_flags[0]) if mode_flags else "dev"
	env.pulse_env = mode
	logger = CLILogger(mode, plain=plain)

	logger.print(f"Generating routes from {app_file}")
	env.codegen_disabled = False
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app = app_ctx.app

	# In CI or prod mode, server_address must be provided
	if (ci or prod) and not app.server_address:
		logger.error(
			"server_address must be provided when generating in CI or production mode. "
			+ "Set it in your App constructor or via the PULSE_SERVER_ADDRESS environment variable."
		)
		raise typer.Exit(1)

	addr = app.server_address or "http://localhost:8000"
	try:
		app.run_codegen(addr)
	except Exception:
		logger.error("Failed to generate routes")
		logger.print_exception()
		raise typer.Exit(1) from None

	route_count = len(app.routes.flat_tree)
	if route_count > 0:
		logger.success(
			f"Generated {route_count} route{'s' if route_count != 1 else ''}"
		)
	else:
		logger.warning("No routes found")


@cli.command("check")
def check(
	app_file: str = typer.Argument(
		..., help="App target: 'path.py[:var]' (default :app) or 'module:var'"
	),
	fix: bool = typer.Option(
		False, "--fix", help="Install missing or outdated dependencies"
	),
	# Mode flags
	dev: bool = typer.Option(False, "--dev", help="Run in development mode"),
	ci: bool = typer.Option(False, "--ci", help="Run in CI mode"),
	prod: bool = typer.Option(False, "--prod", help="Run in production mode"),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
):
	"""Check if web project dependencies are in sync with Pulse app requirements."""
	# Validate mode flags
	mode_flags = [
		name for flag, name in [(dev, "dev"), (ci, "ci"), (prod, "prod")] if flag
	]
	if len(mode_flags) > 1:
		logger = CLILogger("dev", plain=plain)
		logger.error("Please specify only one of --dev, --ci, or --prod.")
		raise typer.Exit(1)

	# Set mode: use specified mode, otherwise dev (default)
	mode: PulseEnv = cast(PulseEnv, mode_flags[0]) if mode_flags else "dev"
	env.pulse_env = mode
	logger = CLILogger(mode, plain=plain)

	logger.print(f"Checking dependencies for {app_file}")
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists():
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	try:
		to_add = check_web_dependencies(
			web_root,
			pulse_version=PULSE_PY_VERSION,
		)
	except DependencyResolutionError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None
	except DependencyError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None

	if not to_add:
		logger.success("Dependencies in sync")
		return

	logger.print("Missing dependencies:")
	for pkg in to_add:
		logger.print(f"  {pkg}")

	if not fix:
		logger.print("Run 'pulse check --fix' to install")
		return

	# Apply fix
	try:
		dep_plan = prepare_web_dependencies(
			web_root,
			pulse_version=PULSE_PY_VERSION,
		)
		if dep_plan:
			_run_dependency_plan(logger, web_root, dep_plan)
		logger.success("Dependencies synced")
	except subprocess.CalledProcessError:
		logger.error("Failed to install web dependencies with Bun.")
		raise typer.Exit(1) from None


@cli.command("init")
def init(
	directory: str = typer.Argument(
		".", help="Directory for the new Pulse project (default: current directory)"
	),
	managed: bool = typer.Option(
		False, "--managed", help="Use managed mode (default: exported mode)"
	),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
):
	"""Create a new Pulse project with minimal scaffolding."""
	env.pulse_env = "dev"
	logger = CLILogger("dev", plain=plain)

	# Resolve directory path
	project_dir = Path(directory).resolve()
	if project_dir.exists() and any(project_dir.iterdir()):
		logger.error(f"Directory {project_dir} is not empty")
		raise typer.Exit(1)

	# Create directory if needed
	project_dir.mkdir(parents=True, exist_ok=True)
	logger.print(f"Creating Pulse project in {project_dir}")

	# Determine mode
	mode = "managed" if managed else "exported"

	# Generate pyproject.toml
	_generate_pyproject_toml(project_dir)

	# Generate app.py
	_generate_app_py(project_dir, mode)

	# Generate web directory structure
	_generate_web_directory(project_dir, mode)

	logger.success("Pulse project created")
	logger.print("Next steps:")
	logger.print(f"  1. cd {project_dir}")
	logger.print("  2. uv sync")
	logger.print("  3. pulse dev app.py")


def _generate_pyproject_toml(project_dir: Path) -> None:
	"""Generate pyproject.toml for a new Pulse project."""
	content = """{
	"project": {
		"name": "pulse-app",
		"version": "0.1.0",
		"dependencies": [
			"pulse @ file://<local-path-to-pulse>"
		]
	},
	"build-system": {
		"requires": ["setuptools", "wheel"],
		"build-backend": "setuptools.build_meta"
	}
}
"""
	(project_dir / "pyproject.toml").write_text(content)


def _generate_app_py(project_dir: Path, mode: str) -> None:
	"""Generate app.py for a new Pulse project."""
	content = f'''from pathlib import Path

import pulse as ps


@ps.component
def Home():
	return ps.div(className="min-h-screen bg-white p-8 flex items-center justify-center")[
		ps.div(className="space-y-4")[
			ps.h1("Welcome to Pulse", className="text-3xl font-bold"),
			ps.p("Edit app.py to get started", className="text-gray-600"),
		],
	]


app = ps.App(
	[ps.Route("/", Home)],
	codegen=ps.CodegenConfig(
		web_dir=Path(__file__).parent / "web",
		mode="{mode}",
	),
)
'''
	(project_dir / "app.py").write_text(content)


def _generate_web_directory(project_dir: Path, mode: str) -> None:
	"""Generate web directory structure for a new Pulse project."""
	web_dir = project_dir / "web"
	web_dir.mkdir(exist_ok=True)

	# Generate package.json
	package_json = """{
	"name": "pulse-app",
	"private": true,
	"type": "module",
	"scripts": {
		"dev": "vite",
		"build": "vite build",
		"typecheck": "tsc --noEmit"
	},
	"dependencies": {
		"pulse-ui-client": "0.1.54",
		"react": "^19.1.0",
		"react-dom": "^19.1.0"
	},
	"devDependencies": {
		"@types/react": "^19.1.2",
		"@types/react-dom": "^19.1.2",
		"typescript": "^5.8.3",
		"vite": "^6.3.3"
	}
}
"""
	(web_dir / "package.json").write_text(package_json)

	# Generate tsconfig.json
	tsconfig = """{
	"compilerOptions": {
		"target": "ES2020",
		"useDefineForClassFields": true,
		"lib": ["ES2020", "DOM", "DOM.Iterable"],
		"module": "ESNext",
		"skipLibCheck": true,
		"esModuleInterop": true,
		"resolveJsonModule": true,
		"moduleResolution": "bundler",
		"allowImportingTsExtensions": true,
		"strict": true,
		"noEmit": true,
		"jsx": "react-jsx",
		"jsxImportSource": "react"
	},
	"include": ["src"],
	"references": [{ "path": "./tsconfig.app.json" }]
}
"""
	(web_dir / "tsconfig.json").write_text(tsconfig)

	# Generate tsconfig.app.json
	tsconfig_app = """{
	"compilerOptions": {
		"composite": true,
		"skipLibCheck": true,
		"esModuleInterop": true,
		"allowSyntheticDefaultImports": true
	},
	"include": ["src"],
	"references": [{ "path": "./tsconfig.json" }]
}
"""
	(web_dir / "tsconfig.app.json").write_text(tsconfig_app)

	# Generate vite.config.ts
	vite_config = """import { defineConfig } from "vite";

export default defineConfig({
	server: {
		middlewareMode: false,
		port: 5173,
		hmr: {
			port: 5173,
		},
	},
});
"""
	(web_dir / "vite.config.ts").write_text(vite_config)

	# Generate index.html
	index_html = """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1.0" />
	<title>Pulse App</title>
</head>
<body>
	<div id="root"></div>
	<script type="module" src="/src/client.ts"></script>
</body>
</html>
"""
	(web_dir / "index.html").write_text(index_html)

	# Create src directory
	src_dir = web_dir / "src"
	src_dir.mkdir(exist_ok=True)

	# Generate client.ts
	client_ts = """import { initPulseClient } from "pulse-ui-client";

initPulseClient({
	wsUrl: `ws://${window.location.hostname}:8000/ws`,
});
"""
	(src_dir / "client.ts").write_text(client_ts)

	# Create server directory
	server_dir = src_dir / "server"
	server_dir.mkdir(exist_ok=True)

	# Generate server.ts
	server_ts = """import { Bun } from "bun";
import { renderVdom } from "pulse-ui-client";

const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3001;

Bun.serve({
	port: PORT,
	async fetch(req: Request) {
		if (req.method !== "POST") {
			return new Response("Method Not Allowed", { status: 405 });
		}

		try {
			const body = await req.json();
			const { vdom, config } = body;

			const html = await renderVdom(vdom, config);
			return new Response(html, {
				headers: { "Content-Type": "text/html; charset=utf-8" },
			});
		} catch (error) {
			console.error("Render error:", error);
			const message = error instanceof Error ? error.message : "Unknown error";
			return new Response(
				JSON.stringify({ error: message }),
				{ status: 500, headers: { "Content-Type": "application/json" } }
			);
		}
	},
});

console.log(`Bun render server listening on port ${PORT}`);
"""
	(server_dir / "server.ts").write_text(server_ts)

	# Generate .gitignore
	gitignore_content = ".pulse/\n"
	(web_dir / ".gitignore").write_text(gitignore_content)


def build_uvicorn_command(
	*,
	app_ctx: AppLoadResult,
	address: str,
	port: int,
	reload_enabled: bool,
	extra_args: Sequence[str],
	dev_secret: str | None,
	server_only: bool,
	web_root: Path,
	verbose: bool = False,
	ready_pattern: str | None = None,
	on_ready: Callable[[], None] | None = None,
) -> CommandSpec:
	app_import = f"{app_ctx.module_name}:{app_ctx.app_var}.asgi_factory"
	args: list[str] = [
		sys.executable,
		"-m",
		"uvicorn",
		app_import,
		"--host",
		address,
		"--port",
		str(port),
		"--factory",
	]

	if reload_enabled:
		args.append("--reload")
		args.extend(["--reload-include", "*.css"])
		app_dir = app_ctx.app_dir or Path.cwd()
		args.extend(["--reload-dir", str(app_dir)])
		if web_root.exists():
			args.extend(["--reload-dir", str(web_root)])

	if app_ctx.app.env == "prod":
		args.extend(production_flags())

	if extra_args:
		args.extend(extra_args)

	command_env = os.environ.copy()
	command_env.update(
		{
			"FORCE_COLOR": "1",
			"PYTHONUNBUFFERED": "1",
			ENV_PULSE_HOST: address,
			ENV_PULSE_PORT: str(port),
		}
	)
	# Pass React server address to uvicorn process if set
	if ENV_PULSE_REACT_SERVER_ADDRESS in os.environ:
		command_env[ENV_PULSE_REACT_SERVER_ADDRESS] = os.environ[
			ENV_PULSE_REACT_SERVER_ADDRESS
		]
	if app_ctx.app.env == "prod" and server_only:
		command_env[ENV_PULSE_DISABLE_CODEGEN] = "1"
	if dev_secret:
		command_env[ENV_PULSE_SECRET] = dev_secret

	cwd = app_ctx.server_cwd or app_ctx.app_dir or Path.cwd()

	# Apply custom log config to filter noisy requests (dev/ci only)
	if app_ctx.app.env != "prod" and not verbose:
		import json
		import tempfile

		log_config = get_log_config()
		log_config_file = Path(tempfile.gettempdir()) / "pulse_uvicorn_log_config.json"
		log_config_file.write_text(json.dumps(log_config))
		args.extend(["--log-config", str(log_config_file)])

	return CommandSpec(
		name="server",
		args=args,
		cwd=cwd,
		env=command_env,
		ready_pattern=ready_pattern,
		on_ready=on_ready,
	)


def build_web_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	port: int | None = None,
	mode: PulseEnv = "dev",
	ready_pattern: str | None = None,
	on_ready: Callable[[], None] | None = None,
) -> CommandSpec:
	command_env = os.environ.copy()
	if mode == "prod":
		# Production: use built server
		args = ["bun", "run", "start"]
	else:
		# Development: use dev server
		args = ["bun", "run", "dev"]

	if port is not None:
		if mode == "prod":
			# react-router-serve uses PORT environment variable
			# Don't add --port flag for production
			command_env["PORT"] = str(port)
		else:
			# react-router dev accepts --port flag
			args.extend(["--port", str(port)])
	if extra_args:
		args.extend(extra_args)

	command_env.update(
		{
			"FORCE_COLOR": "1",
			"PYTHONUNBUFFERED": "1",
		}
	)

	return CommandSpec(
		name="web",
		args=args,
		cwd=web_root,
		env=command_env,
		ready_pattern=ready_pattern,
		on_ready=on_ready,
	)


def _compile_bun_server(logger: CLILogger, web_root: Path, mode: str) -> None:
	"""Compile Bun SSR server to standalone executable."""
	logger.print("Compiling Bun SSR server...")

	# Determine source and output paths based on mode
	if mode == "managed":
		server_dir = web_root / "src" / "server"
		output_dir = web_root / ".." / ".." / "server"  # .pulse/web/server/
	else:
		server_dir = web_root / "src" / "server"
		output_dir = web_root / ".." / "server"  # web/server/

	# Ensure server source exists
	server_ts = server_dir / "server.ts"
	if not server_ts.exists():
		logger.warning(f"SSR server not found at {server_ts}, skipping compilation")
		return

	# Create output directory
	output_dir.mkdir(parents=True, exist_ok=True)

	# Determine executable name (platform-specific)
	exe_name = "server.exe" if sys.platform == "win32" else "server"
	output_path = output_dir / exe_name

	# Run bun build --compile
	try:
		result = subprocess.run(
			[
				"bun",
				"build",
				"--compile",
				"--outfile",
				str(output_path),
				str(server_ts),
			],
			cwd=web_root,
			capture_output=True,
			text=True,
			timeout=120,
		)
		if result.returncode != 0:
			logger.error("Failed to compile Bun SSR server")
			logger.print(result.stderr or result.stdout)
			raise typer.Exit(1)
		logger.success(f"Bun SSR server compiled: {output_path}")
	except subprocess.TimeoutExpired:
		logger.error("Bun compilation timed out")
		raise typer.Exit(1) from None
	except subprocess.CalledProcessError as exc:
		logger.error(f"Bun compilation failed: {exc}")
		raise typer.Exit(1) from None


def _apply_app_context_to_env(app_ctx: AppLoadResult) -> None:
	if app_ctx.app_file:
		env.pulse_app_file = str(app_ctx.app_file)
	if app_ctx.app_dir:
		env.pulse_app_dir = str(app_ctx.app_dir)


def _run_dependency_plan(
	logger: CLILogger, web_root: Path, plan: DependencyPlan
) -> None:
	if plan.to_add:
		logger.print(f"Installing dependencies in {web_root}")
	subprocess.run(plan.command, cwd=web_root, check=True)


def main():
	"""Main CLI entry point."""
	try:
		cli()
	except SystemExit:
		# Let typer.Exit and sys.exit propagate normally (no traceback)
		raise
	except Exception:
		logger = CLILogger(env.pulse_env)
		logger.print_exception()
		sys.exit(1)


def production_flags():
	# Prefer uvloop/http tools automatically if installed
	flags: list[str] = []
	try:
		__import__("uvloop")  # runtime check only
		flags.extend(["--loop", "uvloop"])
	except Exception:
		pass
	try:
		__import__("httptools")
		flags.extend(["--http", "httptools"])
	except Exception:
		pass
	return flags


if __name__ == "__main__":
	main()
