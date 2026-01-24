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
	ENV_PULSE_ASSET_SERVER_ADDRESS,
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
	ENV_PULSE_SECRET,
	ENV_PULSE_SSR_SERVER_ADDRESS,
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


def _run_servers(
	*,
	ctx: typer.Context,
	app_file: str,
	address: str,
	port: int,
	mode: PulseEnv,
	plain: bool,
	server_only: bool,
	web_only: bool,
	asset_server_address: str | None,
	ssr_server_address: str | None,
	reload: bool | None,
	find_port: bool,
	verbose: bool,
	allow_assets: bool,
	ssr_script: str,
) -> None:
	extra_flags = list(ctx.args)

	env.pulse_env = mode
	logger = CLILogger(mode, plain=plain)

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

	if is_single_server and server_only:
		if not ssr_server_address:
			logger.error(
				"--ssr-server-address is required when using single-server mode with --server-only."
			)
			raise typer.Exit(1)
		os.environ[ENV_PULSE_SSR_SERVER_ADDRESS] = ssr_server_address
		if allow_assets and env.pulse_env == "dev":
			if asset_server_address:
				os.environ[ENV_PULSE_ASSET_SERVER_ADDRESS] = asset_server_address
			else:
				logger.error(
					"--asset-server-address is required in dev when using single-server mode with --server-only."
				)
				raise typer.Exit(1)

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists() and not server_only:
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	dev_secret: str | None = None
	if app_instance.env != "prod":
		dev_secret = os.environ.get(ENV_PULSE_SECRET) or resolve_dev_secret(
			web_root if web_root.exists() else app_ctx.app_file
		)

	if env.pulse_env == "dev" and not server_only and allow_assets:
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

	server_ready = {"server": False, "assets": False, "ssr": False}
	announced = False

	def mark_assets_ready() -> None:
		server_ready["assets"] = True
		check_and_announce()

	def mark_ssr_ready() -> None:
		server_ready["ssr"] = True
		check_and_announce()

	def mark_server_ready() -> None:
		server_ready["server"] = True
		check_and_announce()

	def check_and_announce() -> None:
		nonlocal announced
		if announced:
			return

		needs_server = not web_only
		needs_assets = allow_assets and not server_only
		needs_ssr = not server_only

		if needs_server and not server_ready["server"]:
			return
		if needs_assets and not server_ready["assets"]:
			return
		if needs_ssr and not server_ready["ssr"]:
			return

		announced = True
		protocol = "http" if address in ("127.0.0.1", "localhost") else "https"
		server_url = f"{protocol}://{address}:{port}"
		logger.write_ready_announcement(address, port, server_url)

	if not server_only:
		if allow_assets:
			asset_port = find_available_port(5173)
			asset_cmd = build_asset_command(
				web_root=web_root,
				extra_args=web_args,
				port=asset_port,
				ready_pattern=r"localhost:\d+",
				on_ready=mark_assets_ready,
				plain=plain,
			)
			commands.append(asset_cmd)
			env.asset_server_address = f"http://localhost:{asset_port}"
		ssr_port = find_available_port(3001)
		ssr_cmd = build_ssr_command(
			web_root=web_root,
			extra_args=web_args,
			port=ssr_port,
			ready_pattern=r"SSR server running",
			on_ready=mark_ssr_ready,
			plain=plain,
			script=ssr_script,
		)
		commands.append(ssr_cmd)
		env.ssr_server_address = f"http://localhost:{ssr_port}"

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
			plain=plain,
		)
		commands.append(server_cmd)

	exit_code = 0
	with FolderLock(web_root):
		try:
			exit_code = execute_commands(
				commands,
				tag_mode=logger.get_tag_mode(),
			)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
	if exit_code:
		raise typer.Exit(exit_code)


@cli.command(
	"dev", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def dev(
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
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
	server_only: bool = typer.Option(False, "--server-only", "--backend-only"),
	web_only: bool = typer.Option(False, "--web-only"),
	asset_server_address: str | None = typer.Option(
		None,
		"--asset-server-address",
		help="Full URL of asset dev server (required for single-server + --server-only)",
	),
	ssr_server_address: str | None = typer.Option(
		None,
		"--ssr-server-address",
		help="Full URL of SSR server (required for single-server + --server-only)",
	),
	reload: bool | None = typer.Option(None, "--reload/--no-reload"),
	find_port: bool = typer.Option(True, "--find-port/--no-find-port"),
	verbose: bool = typer.Option(
		False, "--verbose", help="Show all logs without filtering"
	),
):
	"""Run Pulse in development mode (server + Vite + SSR)."""
	_run_servers(
		ctx=ctx,
		app_file=app_file,
		address=address,
		port=port,
		mode="dev",
		plain=plain,
		server_only=server_only,
		web_only=web_only,
		asset_server_address=asset_server_address,
		ssr_server_address=ssr_server_address,
		reload=reload,
		find_port=find_port,
		verbose=verbose,
		allow_assets=True,
		ssr_script="ssr",
	)


@cli.command(
	"start", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def start(
	ctx: typer.Context,
	app_file: str = typer.Argument(
		...,
		help=("App target: 'path/to/app.py[:var]' (default :app) or 'module.path:var'"),
	),
	address: str = typer.Option(
		"0.0.0.0",
		"--address",
		help="Host uvicorn binds to",
	),
	port: int = typer.Option(8000, "--port", help="Port uvicorn binds to"),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
	server_only: bool = typer.Option(False, "--server-only", "--backend-only"),
	web_only: bool = typer.Option(False, "--web-only"),
	ssr_server_address: str | None = typer.Option(
		None,
		"--ssr-server-address",
		help="Full URL of SSR server (required for single-server + --server-only)",
	),
	reload: bool | None = typer.Option(None, "--reload/--no-reload"),
	find_port: bool = typer.Option(False, "--find-port/--no-find-port"),
	verbose: bool = typer.Option(
		False, "--verbose", help="Show all logs without filtering"
	),
):
	"""Start Pulse in production mode (server + SSR)."""
	_run_servers(
		ctx=ctx,
		app_file=app_file,
		address=address,
		port=port,
		mode="prod",
		plain=plain,
		server_only=server_only,
		web_only=web_only,
		asset_server_address=None,
		ssr_server_address=ssr_server_address,
		reload=reload,
		find_port=find_port,
		verbose=verbose,
		allow_assets=False,
		ssr_script="start",
	)


@cli.command(
	"build", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def build(
	ctx: typer.Context,
	app_file: str = typer.Argument(
		...,
		help=("App target: 'path/to/app.py[:var]' (default :app) or 'module.path:var'"),
	),
	plain: bool = typer.Option(
		False, "--plain", help="Use plain output without colors or emojis"
	),
	fix: bool = typer.Option(
		False, "--fix", help="Install missing or outdated dependencies before building"
	),
	ci: bool = typer.Option(False, "--ci", help="Run build in CI mode"),
	prod: bool = typer.Option(False, "--prod", help="Run build in production mode"),
):
	"""Generate routes and build web assets."""
	extra_args = list(ctx.args)

	mode_flags = [name for flag, name in [(ci, "ci"), (prod, "prod")] if flag]
	if len(mode_flags) > 1:
		logger = CLILogger("dev", plain=plain)
		logger.error("Please specify only one of --ci or --prod.")
		raise typer.Exit(1)

	mode: PulseEnv = cast(PulseEnv, mode_flags[0]) if mode_flags else "prod"
	env.pulse_env = mode
	logger = CLILogger(mode, plain=plain)

	logger.print(f"Loading app from {app_file}")
	env.codegen_disabled = False
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app = app_ctx.app

	web_root = app.codegen.cfg.web_root
	if not web_root.exists():
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	if mode in ("ci", "prod") and not app.server_address:
		logger.error(
			"server_address must be provided when building in CI or production mode. "
			+ "Set it in your App constructor or via the PULSE_SERVER_ADDRESS environment variable."
		)
		raise typer.Exit(1)

	addr = app.server_address or "http://localhost:8000"
	internal_address = app.internal_server_address or addr

	try:
		app.run_codegen(addr, internal_address)
	except Exception:
		logger.error("Failed to generate routes")
		logger.print_exception()
		raise typer.Exit(1) from None

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
		if not fix:
			logger.error("Missing dependencies detected in web project.")
			for pkg in to_add:
				logger.print(f"  {pkg}")
			logger.print("Run 'pulse build --fix' or 'pulse check --fix' to install.")
			raise typer.Exit(1)
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

	command = build_web_command(
		web_root=web_root,
		extra_args=extra_args,
		plain=plain,
	)
	exit_code = 0
	with FolderLock(web_root):
		try:
			exit_code = execute_commands(
				[command],
				tag_mode=logger.get_tag_mode(),
			)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
	if exit_code:
		raise typer.Exit(exit_code)


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
	plain: bool = False,
) -> CommandSpec:
	cwd = app_ctx.server_cwd or app_ctx.app_dir or Path.cwd()
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
			pulse_dir = str(app_ctx.app.codegen.cfg.pulse_dir)
			pulse_app_dir = web_root / "app" / pulse_dir
			rel_path = Path(os.path.relpath(pulse_app_dir, cwd))
			if not rel_path.is_absolute():
				args.extend(["--reload-exclude", str(rel_path)])
				args.extend(["--reload-exclude", str(rel_path / "**")])

	if app_ctx.app.env == "prod":
		args.extend(production_flags())

	if extra_args:
		args.extend(extra_args)
	if plain:
		args.append("--no-use-colors")

	command_env = os.environ.copy()
	command_env.update(
		{
			"PYTHONUNBUFFERED": "1",
			ENV_PULSE_HOST: address,
			ENV_PULSE_PORT: str(port),
		}
	)
	if plain:
		command_env["NO_COLOR"] = "1"
		command_env["FORCE_COLOR"] = "0"
	else:
		command_env["FORCE_COLOR"] = "1"
	# Pass asset + SSR server addresses to uvicorn process if set
	if ENV_PULSE_ASSET_SERVER_ADDRESS in os.environ:
		command_env[ENV_PULSE_ASSET_SERVER_ADDRESS] = os.environ[
			ENV_PULSE_ASSET_SERVER_ADDRESS
		]
	if ENV_PULSE_SSR_SERVER_ADDRESS in os.environ:
		command_env[ENV_PULSE_SSR_SERVER_ADDRESS] = os.environ[
			ENV_PULSE_SSR_SERVER_ADDRESS
		]
	if app_ctx.app.env == "prod" and server_only:
		command_env[ENV_PULSE_DISABLE_CODEGEN] = "1"
	if dev_secret:
		command_env[ENV_PULSE_SECRET] = dev_secret

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


def build_asset_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	port: int | None = None,
	ready_pattern: str | None = None,
	on_ready: Callable[[], None] | None = None,
	plain: bool = False,
) -> CommandSpec:
	command_env = os.environ.copy()
	# Development: use Vite dev server
	args = ["bun", "run", "dev"]
	if port is not None:
		args.extend(["--port", str(port)])
	if extra_args:
		args.extend(extra_args)

	command_env.update(
		{
			"PYTHONUNBUFFERED": "1",
		}
	)
	if plain:
		command_env["NO_COLOR"] = "1"
		command_env["FORCE_COLOR"] = "0"
	else:
		command_env["FORCE_COLOR"] = "1"

	return CommandSpec(
		name="assets",
		args=args,
		cwd=web_root,
		env=command_env,
		ready_pattern=ready_pattern,
		on_ready=on_ready,
	)


def build_ssr_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	script: str = "ssr",
	port: int | None = None,
	ready_pattern: str | None = None,
	on_ready: Callable[[], None] | None = None,
	plain: bool = False,
) -> CommandSpec:
	command_env = os.environ.copy()
	args = ["bun", "run", script]
	if port is not None:
		command_env["PULSE_SSR_PORT"] = str(port)
	if extra_args:
		args.extend(extra_args)

	command_env.update({"PYTHONUNBUFFERED": "1"})
	if plain:
		command_env["NO_COLOR"] = "1"
		command_env["FORCE_COLOR"] = "0"
	else:
		command_env["FORCE_COLOR"] = "1"

	return CommandSpec(
		name="ssr",
		args=args,
		cwd=web_root,
		env=command_env,
		ready_pattern=ready_pattern,
		on_ready=on_ready,
	)


def build_web_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	plain: bool = False,
) -> CommandSpec:
	command_env = os.environ.copy()
	args = ["bun", "run", "build"]
	if extra_args:
		args.extend(extra_args)

	command_env.update({"PYTHONUNBUFFERED": "1"})
	if plain:
		command_env["NO_COLOR"] = "1"
		command_env["FORCE_COLOR"] = "0"
	else:
		command_env["FORCE_COLOR"] = "1"

	return CommandSpec(
		name="build",
		args=args,
		cwd=web_root,
		env=command_env,
	)


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
