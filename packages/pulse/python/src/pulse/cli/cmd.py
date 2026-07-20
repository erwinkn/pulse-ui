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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast

import typer

from pulse.cli.dependencies import (
	DependencyError,
	DependencyPlan,
	check_web_dependencies,
	prepare_web_dependencies,
)
from pulse.cli.helpers import load_app_from_target
from pulse.cli.lock import FolderLock, active_lock_info, interrupt_active_dev_server
from pulse.cli.logging import CLILogger
from pulse.cli.models import AppLoadResult, CommandSpec
from pulse.cli.processes import execute_commands
from pulse.cli.secrets import resolve_dev_secret
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import (
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
	ENV_PULSE_SECRET,
	ENV_PULSE_SSR_BACKEND_URL,
	ENV_PULSE_WEB_UPSTREAM,
	PulseEnv,
	env,
)
from pulse.helpers import find_available_port, local_server_url
from pulse.origins import normalize_http_origin
from pulse.version import __version__ as PULSE_PY_VERSION

cli = typer.Typer(
	name="pulse",
	help="Pulse UI - Python to TypeScript bridge with server-side callbacks",
	no_args_is_help=True,
)


@dataclass(frozen=True, slots=True)
class RunPlan:
	start_server: bool
	start_web: bool
	server_args: tuple[str, ...]
	web_args: tuple[str, ...]

	@classmethod
	def resolve(
		cls,
		*,
		backend_only: bool,
		web_only: bool,
		extra_args: Sequence[str],
	) -> RunPlan:
		if backend_only and web_only:
			raise ValueError(
				"Cannot use --backend-only and --web-only at the same time."
			)
		args = tuple(extra_args)
		return cls(
			start_server=not web_only,
			start_web=not backend_only,
			server_args=args if not web_only else (),
			web_args=args if web_only else (),
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
	backend_only: bool = typer.Option(
		False,
		"--backend-only",
		help="Run only the Pulse backend; do not start or proxy the web server",
	),
	web_only: bool = typer.Option(False, "--web-only"),
	ssr_backend_url: str | None = typer.Option(
		None,
		"--ssr-backend-url",
		help="Internal Pulse backend URL used by a web-only process",
	),
	reload: bool | None = typer.Option(None, "--reload/--no-reload"),
	find_port: bool = typer.Option(True, "--find-port/--no-find-port"),
	interrupt: bool = typer.Option(
		False,
		"--interrupt",
		help="Stop any existing Pulse dev server for this app before starting.",
	),
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

	try:
		plan = RunPlan.resolve(
			backend_only=backend_only,
			web_only=web_only,
			extra_args=extra_flags,
		)
	except ValueError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None

	logger.print(f"Loading app from {app_file}")
	app_ctx = load_app_from_target(app_file, logger)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	resolved_ssr_backend_url: str | None = None
	if not plan.start_server:
		configured_ssr_backend_url = ssr_backend_url or env.ssr_backend_url
		if configured_ssr_backend_url is None:
			logger.error(
				"--ssr-backend-url or PULSE_SSR_BACKEND_URL is required with --web-only."
			)
			raise typer.Exit(1)
		try:
			resolved_ssr_backend_url = normalize_http_origin(
				configured_ssr_backend_url,
				name="SSR backend URL",
			)
		except ValueError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists() and plan.start_web:
		logger.error(f"Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)
	backend_lock_root = (
		app_ctx.app_file.parent
		if app_ctx.app_file is not None
		else (app_ctx.app_dir or Path.cwd())
	)
	lock_root = web_root if plan.start_web else backend_lock_root

	if interrupt:
		try:
			stopped = interrupt_active_dev_server(lock_root)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
		if stopped:
			logger.warning(
				f"Stopped existing Pulse dev server at {stopped.url} (pid={stopped.pid})."
			)

	if find_port:
		port = find_available_port(port)

	dev_secret: str | None = None
	if app_instance.env != "prod":
		dev_secret = os.environ.get(ENV_PULSE_SECRET) or resolve_dev_secret(
			web_root if web_root.exists() else app_ctx.app_file
		)

	commands: list[CommandSpec] = []

	# Track readiness for announcement
	server_ready = {"server": False, "web": False}
	announced = False
	ready_url = local_server_url(address, port)

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

		if plan.start_server and not server_ready["server"]:
			return
		if plan.start_web and not server_ready["web"]:
			return

		# All required servers are ready, show announcement
		announced = True
		logger.write_ready_announcement(ready_url)

	# Build the web command first so the combined server can proxy its port.
	web_upstream: str | None = None
	if plan.start_web:
		web_port = find_available_port(5173)
		if not plan.start_server:
			ready_url = f"http://localhost:{web_port}"
		web_cmd = build_web_command(
			web_root=web_root,
			extra_args=plan.web_args,
			port=web_port,
			mode=app_instance.env,
			ssr_backend_url=(
				resolved_ssr_backend_url
				if not plan.start_server
				else local_server_url(address, port)
			),
			ready_pattern=r"localhost:\d+",
			on_ready=mark_web_ready,
			plain=plain,
		)
		commands.append(web_cmd)
		if plan.start_server:
			web_upstream = f"http://localhost:{web_port}"

	if plan.start_server:
		server_cmd = build_uvicorn_command(
			app_ctx=app_ctx,
			address=address,
			port=port,
			reload_enabled=reload,
			extra_args=plan.server_args,
			dev_secret=dev_secret,
			web_upstream=web_upstream,
			disable_codegen=not plan.start_web,
			web_root=web_root,
			verbose=verbose,
			ready_pattern=r"Application startup complete",
			on_ready=mark_server_ready,
			plain=plain,
		)
		commands.append(server_cmd)

	exit_code = 1
	try:
		with FolderLock(lock_root, address=address, port=port):
			# Install web dependencies and generate route files before launching
			# the web dev server. Without the install, a fresh checkout's web
			# process dies with "react-router: command not found"; without codegen,
			# it reads routes.ts before the server has generated "./pulse/routes"
			# and dies with "Cannot find module './pulse/routes'". Both steps are
			# idempotent and cheap on warm starts, and run under the lock so a
			# rejected concurrent run never rewrites a live instance's files.
			if env.pulse_env == "dev" and plan.start_web:
				try:
					dep_plan = prepare_web_dependencies(
						web_root,
						pulse_version=PULSE_PY_VERSION,
					)
				except DependencyError as exc:
					logger.error(str(exc))
					raise typer.Exit(1) from None
				try:
					_run_dependency_plan(logger, web_root, dep_plan)
				except subprocess.CalledProcessError:
					logger.error("Failed to install web dependencies with Bun.")
					raise typer.Exit(1) from None
				logger.print("Generating routes")
				try:
					app_instance.run_codegen()
				except Exception:
					logger.error("Failed to generate routes")
					logger.print_exception()
					raise typer.Exit(1) from None

			try:
				exit_code = execute_commands(
					commands,
					tag_mode=logger.get_tag_mode(),
				)
			except RuntimeError as exc:
				logger.error(str(exc))
				raise typer.Exit(1) from None
	except typer.Exit:
		raise
	except RuntimeError as exc:
		message = str(exc)
		logger.error(message)
		if message.startswith("Another Pulse dev instance is running at "):
			logger.print("Run again with --interrupt to stop it and start this app.")
		raise typer.Exit(1) from None
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
	web_root = app.codegen.cfg.web_root
	if info := active_lock_info(web_root):
		logger.error(
			"Cannot run 'pulse generate' while a Pulse dev server is running at "
			+ f"{info.url} (pid={info.pid}). Stop the dev server first."
		)
		raise typer.Exit(1)

	try:
		app.run_codegen()
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
	web_upstream: str | None,
	disable_codegen: bool,
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
	command_env.pop(ENV_PULSE_WEB_UPSTREAM, None)
	if web_upstream is not None:
		command_env[ENV_PULSE_WEB_UPSTREAM] = web_upstream
	if disable_codegen:
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


def build_web_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	port: int | None = None,
	mode: PulseEnv = "dev",
	ssr_backend_url: str | None = None,
	ready_pattern: str | None = None,
	on_ready: Callable[[], None] | None = None,
	plain: bool = False,
) -> CommandSpec:
	command_env = os.environ.copy()
	if mode == "prod":
		args = [
			"node",
			"node_modules/@react-router/serve/dist/cli.js",
			"./build/server/index.js",
		]
		command_env["NODE_ENV"] = "production"
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
			"PYTHONUNBUFFERED": "1",
		}
	)
	if ssr_backend_url is not None:
		command_env[ENV_PULSE_SSR_BACKEND_URL] = normalize_http_origin(
			ssr_backend_url,
			name="ssr_backend_url",
		)
	if plain:
		command_env["NO_COLOR"] = "1"
		command_env["FORCE_COLOR"] = "0"
	else:
		command_env["FORCE_COLOR"] = "1"

	return CommandSpec(
		name="web",
		args=args,
		cwd=web_root,
		env=command_env,
		ready_pattern=ready_pattern,
		on_ready=on_ready,
	)


def _apply_app_context_to_env(app_ctx: AppLoadResult) -> None:
	if app_ctx.app_file:
		env.pulse_app_file = str(app_ctx.app_file)
	if app_ctx.app_dir:
		env.pulse_app_dir = str(app_ctx.app_dir)


def _run_dependency_plan(
	logger: CLILogger, web_root: Path, plan: DependencyPlan
) -> None:
	logger.print(f"Installing web dependencies in {web_root}")
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
