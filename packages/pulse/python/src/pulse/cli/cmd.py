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
from typing import cast

import typer
from rich.console import Console

from pulse.cli.dependencies import (
	DependencyError,
	DependencyPlan,
	DependencyResolutionError,
	check_web_dependencies,
	prepare_web_dependencies,
)
from pulse.cli.folder_lock import FolderLock
from pulse.cli.helpers import load_app_from_target
from pulse.cli.models import AppLoadResult, CommandSpec
from pulse.cli.processes import execute_commands
from pulse.cli.secrets import resolve_dev_secret
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import (
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
	dev: bool = typer.Option(False, "--dev", help="Run in development env"),
	ci: bool = typer.Option(False, "--ci", help="Run in CI env"),
	prod: bool = typer.Option(False, "--prod", help="Run in production env"),
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

	env_flags = [
		name for flag, name in [(dev, "dev"), (ci, "ci"), (prod, "prod")] if flag
	]
	if len(env_flags) > 1:
		typer.echo("❌ Please specify only one of --dev, --ci, or --prod.")
		raise typer.Exit(1)
	if ci:
		typer.echo(
			"❌ --ci is not supported for 'pulse run'. Use 'pulse generate --ci' instead."
		)
		raise typer.Exit(1)
	if len(env_flags) == 1:
		env.pulse_env = cast(PulseEnv, env_flags[0])

	# Turn on reload in dev only
	if reload is None:
		reload = env.pulse_env == "dev"

	if server_only and web_only:
		typer.echo("❌ Cannot use --server-only and --web-only at the same time.")
		raise typer.Exit(1)

	if find_port:
		port = find_available_port(port)

	console = Console()
	console.log(f"📁 Loading app from: {app_file}")
	app_ctx = load_app_from_target(app_file)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	is_single_server = app_instance.mode == "single-server"
	if is_single_server:
		console.log("🔧 [cyan]Single-server mode[/cyan]")

	# In single-server + server-only mode, require explicit React server address
	if is_single_server and server_only:
		if not react_server_address:
			typer.echo(
				"❌ --react-server-address is required when using single-server mode with --server-only."
			)
			raise typer.Exit(1)
		os.environ[ENV_PULSE_REACT_SERVER_ADDRESS] = react_server_address

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists() and not server_only:
		console.log(f"❌ Directory not found: {web_root.absolute()}")
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
			console.log(f"❌ {exc}")
			raise typer.Exit(1) from None
		except DependencyError as exc:
			console.log(f"❌ {exc}")
			raise typer.Exit(1) from None

		if to_add:
			try:
				dep_plan = prepare_web_dependencies(
					web_root,
					pulse_version=PULSE_PY_VERSION,
				)
				if dep_plan:
					_run_dependency_plan(console, web_root, dep_plan)
			except subprocess.CalledProcessError:
				console.log("❌ Failed to install web dependencies with Bun.")
				raise typer.Exit(1) from None

	server_args = extra_flags if not web_only else []
	web_args = extra_flags if web_only else []

	commands: list[CommandSpec] = []
	# Build web command first (when needed) so we can set PULSE_REACT_SERVER_ADDRESS
	# before building the uvicorn command, which needs that env var
	if not server_only:
		if is_single_server:
			web_port = find_available_port(5173)
			commands.append(
				build_web_command(
					web_root=web_root,
					extra_args=web_args,
					port=web_port,
					mode=app_instance.env,
				)
			)
			# Set env var so app can read the React server address
			react_server_address = f"http://localhost:{web_port}"
			os.environ[ENV_PULSE_REACT_SERVER_ADDRESS] = react_server_address
		else:
			commands.append(build_web_command(web_root=web_root, extra_args=web_args))

	if not web_only:
		commands.append(
			build_uvicorn_command(
				app_ctx=app_ctx,
				address=address,
				port=port,
				reload_enabled=reload,
				extra_args=server_args,
				dev_secret=dev_secret,
				server_only=server_only,
				console=console,
				web_root=web_root,
				announce_url=is_single_server,
				verbose=verbose,
			)
		)

	# Only add tags in dev mode to avoid breaking structured output (e.g., CloudWatch EMF metrics)
	tag_colors = (
		{"server": "cyan", "web": "orange1"} if env.pulse_env == "dev" else None
	)

	with FolderLock(web_root):
		try:
			exit_code = execute_commands(
				commands,
				console=console,
				tag_colors=tag_colors,
			)
			raise typer.Exit(exit_code)
		except RuntimeError as exc:
			console.log(f"❌ {exc}")
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
):
	"""Generate TypeScript routes without starting the server."""
	console = Console()
	console.log("🔄 Generating TypeScript routes...")

	mode_flags = [
		name for flag, name in [(dev, "dev"), (ci, "ci"), (prod, "prod")] if flag
	]
	if len(mode_flags) > 1:
		typer.echo("❌ Please specify only one of --dev, --ci, or --prod.")
		raise typer.Exit(1)
	if len(mode_flags) == 1:
		env.pulse_env = cast(PulseEnv, mode_flags[0])

	console.log(f"📁 Loading routes from: {app_file}")
	env.codegen_disabled = False
	app_ctx = load_app_from_target(app_file)
	_apply_app_context_to_env(app_ctx)
	app = app_ctx.app
	console.log(f"📋 Found {len(app.routes.flat_tree)} routes")

	# In CI or prod mode, server_address must be provided
	if (ci or prod) and not app.server_address:
		typer.echo(
			"❌ server_address must be provided when generating in CI or production mode. "
			+ "Set it in your App constructor or via the PULSE_SERVER_ADDRESS environment variable."
		)
		raise typer.Exit(1)

	addr = app.server_address or "http://localhost:8000"
	app.run_codegen(addr)

	if len(app.routes.flat_tree) > 0:
		console.log(f"✅ Generated {len(app.routes.flat_tree)} routes successfully!")
	else:
		console.log("⚠️  No routes found to generate")


@cli.command("check")
def check(
	app_file: str = typer.Argument(
		..., help="App target: 'path.py[:var]' (default :app) or 'module:var'"
	),
	fix: bool = typer.Option(
		False, "--fix", help="Install missing or outdated dependencies"
	),
):
	"""Check if web project dependencies are in sync with Pulse app requirements."""
	console = Console()

	console.log(f"📁 Loading app from: {app_file}")
	app_ctx = load_app_from_target(app_file)
	_apply_app_context_to_env(app_ctx)
	app_instance = app_ctx.app

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists():
		console.log(f"❌ Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	try:
		to_add = check_web_dependencies(
			web_root,
			pulse_version=PULSE_PY_VERSION,
		)
	except DependencyResolutionError as exc:
		console.log(f"❌ {exc}")
		raise typer.Exit(1) from None
	except DependencyError as exc:
		console.log(f"❌ {exc}")
		raise typer.Exit(1) from None

	if not to_add:
		console.log("✅ Web dependencies are in sync")
		return

	console.log("📦 Web dependencies are out of sync:")
	for pkg in to_add:
		console.log(f"  - {pkg}")

	if not fix:
		console.log("💡 Run 'pulse check --fix' to install missing dependencies")
		return

	# Apply fix
	try:
		dep_plan = prepare_web_dependencies(
			web_root,
			pulse_version=PULSE_PY_VERSION,
		)
		if dep_plan:
			_run_dependency_plan(console, web_root, dep_plan)
		console.log("✅ Web dependencies synced successfully")
	except subprocess.CalledProcessError:
		console.log("❌ Failed to install web dependencies with Bun.")
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
	console: Console,
	web_root: Path,
	announce_url: bool,
	verbose: bool = False,
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

	def _announce() -> None:
		protocol = "http" if address in ("127.0.0.1", "localhost") else "https"
		server_url = f"{protocol}://{address}:{port}"
		console.log("")
		console.log(
			f"✨ [bold green]Pulse running at:[/bold green] [bold cyan][link={server_url}]{server_url}[/link][/bold cyan]"
		)
		console.log(f"   [dim]API: {server_url}/_pulse/...[/dim]")
		console.log("")

	return CommandSpec(
		name="server",
		args=args,
		cwd=cwd,
		env=command_env,
		on_spawn=_announce if announce_url else None,
	)


def build_web_command(
	*,
	web_root: Path,
	extra_args: Sequence[str],
	port: int | None = None,
	mode: PulseEnv = "dev",
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

	return CommandSpec(name="web", args=args, cwd=web_root, env=command_env)


def _apply_app_context_to_env(app_ctx: AppLoadResult) -> None:
	if app_ctx.app_file:
		env.pulse_app_file = str(app_ctx.app_file)
	if app_ctx.app_dir:
		env.pulse_app_dir = str(app_ctx.app_dir)


def _run_dependency_plan(
	console: Console, web_root: Path, plan: DependencyPlan
) -> None:
	# command_display = " ".join(plan.command)
	if plan.to_add:
		console.log(f"📦 Adding/updating web dependencies in {web_root}")
	else:
		console.log(f"📦 Installing web dependencies in {web_root}")
	subprocess.run(plan.command, cwd=web_root, check=True)


def main():
	"""Main CLI entry point."""
	try:
		cli()
	except Exception:
		console = Console()
		console.print_exception()
		raise typer.Exit(1) from None


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
