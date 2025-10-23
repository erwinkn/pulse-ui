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
	prepare_web_dependencies,
)
from pulse.cli.folder_lock import FolderLock
from pulse.cli.helpers import load_app_from_target
from pulse.cli.models import AppLoadResult, CommandSpec
from pulse.cli.processes import execute_commands
from pulse.cli.secrets import resolve_dev_secret
from pulse.env import (
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
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
		"--bind-address",
		help="Host uvicorn binds to",
	),
	port: int = typer.Option(8000, "--bind-port", help="Port uvicorn binds to"),
	# Env flags
	dev: bool = typer.Option(False, "--dev", help="Run in development env"),
	ci: bool = typer.Option(False, "--ci", help="Run in CI env"),
	prod: bool = typer.Option(False, "--prod", help="Run in production env"),
	server_only: bool = typer.Option(False, "--server-only", "--backend-only"),
	web_only: bool = typer.Option(False, "--web-only"),
	reload: bool = typer.Option(True, "--reload"),
	find_port: bool = typer.Option(True, "--find-port/--no-find-port"),
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

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists() and not server_only:
		console.log(f"❌ Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	dev_secret: str | None = None
	if app_instance.env != "prod":
		dev_secret = os.environ.get(ENV_PULSE_SECRET) or resolve_dev_secret(
			web_root if web_root.exists() else app_ctx.app_file
		)

	if not server_only:
		try:
			dep_plan = prepare_web_dependencies(
				web_root,
				pulse_version=PULSE_PY_VERSION,
			)
		except DependencyResolutionError as exc:
			console.log(f"❌ {exc}")
			raise typer.Exit(1) from None
		except DependencyError as exc:
			console.log(f"❌ {exc}")
			raise typer.Exit(1) from None

		if dep_plan:
			try:
				_run_dependency_plan(console, web_root, dep_plan)
			except subprocess.CalledProcessError:
				console.log("❌ Failed to install web dependencies with Bun.")
				raise typer.Exit(1) from None

	server_args = extra_flags if not web_only else []
	web_args = extra_flags if web_only else []

	commands: list[CommandSpec] = []
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
			)
		)

	if not is_single_server and not server_only:
		commands.append(build_web_command(web_root=web_root, extra_args=web_args))

	tag_colors = {"server": "cyan", "web": "orange1"}

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

	addr = app.server_address or "localhost:8000"
	app.run_codegen(addr)

	if len(app.routes.flat_tree) > 0:
		console.log(f"✅ Generated {len(app.routes.flat_tree)} routes successfully!")
	else:
		console.log("⚠️  No routes found to generate")


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

	if reload_enabled and app_ctx.app.env != "prod":
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
	if app_ctx.app.env == "prod" and server_only:
		command_env[ENV_PULSE_DISABLE_CODEGEN] = "1"
	if dev_secret:
		command_env[ENV_PULSE_SECRET] = dev_secret

	cwd = app_ctx.server_cwd or app_ctx.app_dir or Path.cwd()

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


def build_web_command(*, web_root: Path, extra_args: Sequence[str]) -> CommandSpec:
	args = ["bun", "run", "dev"]
	if extra_args:
		args.extend(extra_args)

	command_env = os.environ.copy()
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
