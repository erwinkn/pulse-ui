"""
Command-line interface for Pulse UI.
This module provides the CLI commands for running the server and generating routes.
"""
# typer relies on function calls used as default values
# pyright: reportCallInDefaultInitializer=false

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, cast

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
from pulse.cli.ports import PortReservation, reserve_port
from pulse.cli.processes import execute_commands
from pulse.cli.reload import DevSupervisor
from pulse.cli.secrets import resolve_dev_secret
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import (
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_HMR_CLIENT_PORT,
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
	ENV_PULSE_REACT_SERVER_ADDRESS,
	ENV_PULSE_SECRET,
	PulseEnv,
	env,
)
from pulse.helpers import find_available_port, local_server_url
from pulse.transpiler.assets import get_registered_assets
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
		help="Public server host",
	),
	port: int = typer.Option(8000, "--port", help="Public server port"),
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

	logger = _configure_run_mode(dev=dev, prod=prod, plain=plain)

	# Turn on reload in dev only
	if reload is None:
		reload = env.pulse_env == "dev"

	_validate_run_options(server_only=server_only, web_only=web_only, logger=logger)

	supervised_reload = env.pulse_env == "dev" and reload and not web_only
	bootstrap_modules: set[str] = set(sys.modules) if supervised_reload else set()
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

	if interrupt:
		try:
			stopped = interrupt_active_dev_server(web_root)
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
		if stopped:
			logger.warning(
				f"Stopped existing Pulse dev server at {stopped.url} (pid={stopped.pid})."
			)

	public_port: PortReservation | None = None
	if supervised_reload:
		try:
			public_port = reserve_port(address, port, find_port=find_port)
			ctx.call_on_close(public_port.close)
			port = public_port.port
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
	elif find_port:
		port = find_available_port(port)

	dev_secret: str | None = None
	if app_instance.env != "prod":
		dev_secret = os.environ.get(ENV_PULSE_SECRET) or resolve_dev_secret(
			web_root if web_root.exists() else app_ctx.app_file
		)

	server_args = extra_flags if not web_only else []
	web_args = extra_flags if web_only else []

	commands: list[CommandSpec] = []
	if supervised_reload and server_args:
		logger.error(
			"Raw Uvicorn arguments are not supported with Pulse reload yet. "
			+ "Use --no-reload to pass them through."
		)
		raise typer.Exit(1)

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
		logger.write_ready_announcement(address, port, local_server_url(address, port))

	# Build web command first (when needed) so we can set PULSE_REACT_SERVER_ADDRESS
	# before building the uvicorn command, which needs that env var
	web_port: int | None = None
	web_port_reservation: PortReservation | None = None
	web_cmd: CommandSpec | None = None
	server_cmd: CommandSpec | None = None
	if not server_only:
		web_host = "127.0.0.1" if is_single_server else address
		try:
			web_port_reservation = reserve_port(web_host, 5173, find_port=find_port)
			ctx.call_on_close(web_port_reservation.close)
			web_port = web_port_reservation.port
		except RuntimeError as exc:
			logger.error(str(exc))
			raise typer.Exit(1) from None
		web_cmd = build_web_command(
			web_root=web_root,
			extra_args=web_args,
			host=web_host,
			port=web_port,
			strict_port=True,
			mode=app_instance.env,
			ready_pattern=(None if supervised_reload else rf":{web_port}(?:[/\s]|$)"),
			on_ready=mark_web_ready,
			plain=plain,
			verbose=verbose,
		)
		if supervised_reload and is_single_server:
			web_cmd.env[ENV_PULSE_HMR_CLIENT_PORT] = str(port)
		if not supervised_reload:
			commands.append(web_cmd)
		env.react_server_address = local_server_url(web_host, web_port)

	if not web_only:
		if supervised_reload:
			server_cmd = build_dev_worker_command(
				app_ctx=app_ctx,
				address=address,
				port=port,
				dev_secret=dev_secret,
				verbose=verbose,
				on_ready=mark_server_ready,
				plain=plain,
			)
		else:
			server_cmd = build_uvicorn_command(
				app_ctx=app_ctx,
				address=address,
				port=port,
				web_root=web_root,
				reload_enabled=reload,
				extra_args=server_args,
				dev_secret=dev_secret,
				server_only=server_only,
				verbose=verbose,
				ready_pattern=r"Application startup complete",
				on_ready=mark_server_ready,
				plain=plain,
			)
		if not supervised_reload:
			commands.append(server_cmd)

	exit_code = 1
	try:
		with FolderLock(web_root, address=address, port=port):
			_prepare_run_dependencies(
				logger=logger,
				web_root=web_root,
				app_instance=app_instance,
				address=address,
				port=port,
				server_only=server_only,
			)

			if supervised_reload:
				assert server_cmd is not None
				watch_root = app_ctx.app_dir or app_ctx.server_cwd or Path.cwd()
				web_root_resolved = web_root.resolve()
				registered_sources = {
					asset.source_path.resolve() for asset in get_registered_assets()
				}
				_release_reload_bootstrap(app_ctx, bootstrap_modules)
				del app_instance
				del app_ctx
				assert public_port is not None
				if web_port_reservation is not None:
					web_port_reservation.close()
				exit_code = _run_supervised(
					server_cmd=server_cmd,
					web_cmd=web_cmd,
					watch_root=watch_root,
					web_root=web_root,
					web_root_resolved=web_root_resolved,
					registered_sources=registered_sources,
					logger=logger,
					public_port=public_port,
				)
			else:
				exit_code = _run_commands(
					commands=commands,
					web_port_reservation=web_port_reservation,
					logger=logger,
				)
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
	web_root: Path,
	reload_enabled: bool,
	extra_args: Sequence[str],
	dev_secret: str | None,
	server_only: bool,
	verbose: bool = False,
	ready_pattern: str | None = None,
	on_ready: Callable[[], None] | None = None,
	plain: bool = False,
) -> CommandSpec:
	cwd, command_env = _server_process_context(
		app_ctx=app_ctx,
		address=address,
		port=port,
		dev_secret=dev_secret,
		plain=plain,
	)
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

	if app_ctx.app.env == "prod" and server_only:
		command_env[ENV_PULSE_DISABLE_CODEGEN] = "1"

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


def build_dev_worker_command(
	*,
	app_ctx: AppLoadResult,
	address: str,
	port: int,
	dev_secret: str | None,
	verbose: bool,
	on_ready: Callable[[], None] | None = None,
	plain: bool = False,
) -> CommandSpec:
	cwd, command_env = _server_process_context(
		app_ctx=app_ctx,
		address=address,
		port=port,
		dev_secret=dev_secret,
		plain=plain,
	)
	target = app_ctx.target
	if app_ctx.mode == "path" and app_ctx.app_file is not None:
		target = f"{app_ctx.app_file}:{app_ctx.app_var}"
	args = [
		sys.executable,
		"-m",
		"pulse.cli.dev_worker",
		"--target",
		target,
		"--host",
		address,
		"--port",
		str(port),
	]
	if plain:
		args.append("--plain")
	if verbose:
		args.append("--verbose")
	return CommandSpec(
		name="server",
		args=args,
		cwd=cwd,
		env=command_env,
		on_ready=on_ready,
	)


def _server_process_context(
	*,
	app_ctx: AppLoadResult,
	address: str,
	port: int,
	dev_secret: str | None,
	plain: bool,
) -> tuple[Path, dict[str, str]]:
	cwd = app_ctx.server_cwd or app_ctx.app_dir or Path.cwd()
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
	if ENV_PULSE_REACT_SERVER_ADDRESS in os.environ:
		command_env[ENV_PULSE_REACT_SERVER_ADDRESS] = os.environ[
			ENV_PULSE_REACT_SERVER_ADDRESS
		]
	if dev_secret:
		command_env[ENV_PULSE_SECRET] = dev_secret
	return cwd, command_env


def build_web_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	host: str | None = None,
	port: int | None = None,
	strict_port: bool = True,
	mode: PulseEnv = "dev",
	verbose: bool = False,
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
		if host is not None:
			command_env["HOST"] = host
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
			if strict_port:
				args.append("--strictPort")
	if extra_args:
		args.extend(extra_args)
	if mode != "prod" and host is not None:
		args.extend(["--host", host])

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

	output_filters = (
		()
		if verbose
		else (
			"Network: use --host to expose",
			"press h + enter to show help",
			"➜  Local:",
			"/__manifest",
			"?import",
		)
	)
	return CommandSpec(
		name="web",
		args=args,
		cwd=web_root,
		env=command_env,
		ready_pattern=ready_pattern,
		on_ready=on_ready,
		output_filters=output_filters,
	)


def _configure_run_mode(*, dev: bool, prod: bool, plain: bool) -> CLILogger:
	if dev and prod:
		logger = CLILogger("dev", plain=plain)
		logger.error("Please specify only one of --dev or --prod.")
		raise typer.Exit(1)

	mode: PulseEnv = "prod" if prod else "dev"
	env.pulse_env = mode
	return CLILogger(mode, plain=plain)


def _validate_run_options(
	*, server_only: bool, web_only: bool, logger: CLILogger
) -> None:
	if server_only and web_only:
		logger.error("Cannot use --server-only and --web-only at the same time.")
		raise typer.Exit(1)


def _prepare_run_dependencies(
	*,
	logger: CLILogger,
	web_root: Path,
	app_instance: Any,
	address: str,
	port: int,
	server_only: bool,
) -> None:
	if env.pulse_env != "dev" or server_only:
		return
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
		app_instance.run_codegen(local_server_url(address, port))
	except Exception:
		logger.error("Failed to generate routes")
		logger.print_exception()
		raise typer.Exit(1) from None


def _run_supervised(
	*,
	server_cmd: CommandSpec,
	web_cmd: CommandSpec | None,
	watch_root: Path,
	web_root: Path,
	web_root_resolved: Path,
	registered_sources: set[Path],
	logger: CLILogger,
	public_port: PortReservation,
) -> int:
	return asyncio.run(
		DevSupervisor(
			backend=server_cmd,
			web=web_cmd,
			watch_roots=(watch_root,),
			ignored_roots=(web_root_resolved,),
			registered_sources=registered_sources,
			tag_mode=logger.get_tag_mode(),
			listeners=public_port.sockets,
			web_root=web_root,
		).run()
	)


def _run_commands(
	*,
	commands: list[CommandSpec],
	web_port_reservation: PortReservation | None,
	logger: CLILogger,
) -> int:
	try:
		if web_port_reservation is not None:
			web_port_reservation.close()
		return execute_commands(commands, tag_mode=logger.get_tag_mode())
	except RuntimeError as exc:
		logger.error(str(exc))
		raise typer.Exit(1) from None


def _apply_app_context_to_env(app_ctx: AppLoadResult) -> None:
	if app_ctx.app_file:
		env.pulse_app_file = str(app_ctx.app_file)
	if app_ctx.app_dir:
		env.pulse_app_dir = str(app_ctx.app_dir)


def _release_reload_bootstrap(
	app_ctx: AppLoadResult, modules_before_load: set[str]
) -> None:
	if app_ctx.app_dir is None:
		return
	app_dir = app_ctx.app_dir.resolve()
	for name in set(sys.modules).difference(modules_before_load):
		module = sys.modules.get(name)
		module_file = vars(module).get("__file__") if module is not None else None
		if not isinstance(module_file, str):
			continue
		path = Path(module_file).resolve()
		if path == app_dir or path.is_relative_to(app_dir):
			sys.modules.pop(name, None)


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
