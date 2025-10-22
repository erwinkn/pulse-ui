"""
Command-line interface for Pulse UI.
This module provides the CLI commands for running the server and generating routes.
"""
# typer relies on function calls used as default values
# pyright: reportCallInDefaultInitializer=false

import os
import pty as pty_module
import subprocess
import sys
from pathlib import Path
from typing import cast

import typer
from rich.console import Console

from pulse.cli.helpers import (
	find_available_port,
	load_app_from_target,
	parse_app_target,
)
from pulse.cli.packages import (
	VersionConflict,
	get_pkg_spec,
	is_workspace_spec,
	load_package_json,
	parse_dependency_spec,
	parse_install_spec,
	resolve_versions,
	spec_satisfies,
)
from pulse.env import (
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_HOST,
	ENV_PULSE_LOCK_MANAGED_BY_CLI,
	ENV_PULSE_PORT,
	ENV_PULSE_SECRET,
	PulseMode,
	env,
)
from pulse.helpers import (
	ensure_web_lock,
	lock_path_for_web_root,
	remove_web_lock,
)
from pulse.react_component import registered_react_components
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
	# Mode flags
	dev: bool = typer.Option(False, "--dev", help="Run in development mode"),
	ci: bool = typer.Option(False, "--ci", help="Run in CI mode"),
	prod: bool = typer.Option(False, "--prod", help="Run in production mode"),
	server_only: bool = typer.Option(False, "--server-only", "--backend-only"),
	web_only: bool = typer.Option(False, "--web-only"),
	reload: bool = typer.Option(True, "--reload"),
	find_port: bool = typer.Option(True, "--find-port/--no-find-port"),
):
	"""Run the Pulse server and web development server together."""
	# Extra flags to pass through
	extra_flags = ctx.args

	# Validate and set mode based on flags
	mode_flags = [
		name for flag, name in [(dev, "dev"), (ci, "ci"), (prod, "prod")] if flag
	]
	if len(mode_flags) > 1:
		typer.echo("❌ Please specify only one of --dev, --ci, or --prod.")
		raise typer.Exit(1)
	# Disallow CI mode for `pulse run`
	if ci:
		typer.echo(
			"❌ --ci is not supported for 'pulse run'. Use 'pulse generate --ci' instead."
		)
		raise typer.Exit(1)
	if len(mode_flags) == 1:
		env.pulse_mode = cast(PulseMode, mode_flags[0])

	if server_only and web_only:
		typer.echo("❌ Cannot use --server-only and --web-only at the same time.")
		raise typer.Exit(1)

	# Only pick a free port for the bind port (public port is unchanged)
	if find_port:
		port = find_available_port(port)

	console = Console()
	console.log(f"📁 Loading app from: {app_file}")
	parsed = parse_app_target(app_file)
	app_instance = load_app_from_target(app_file)

	web_root = app_instance.codegen.cfg.web_root
	if not web_root.exists() and not server_only:
		console.log(f"❌ Directory not found: {web_root.absolute()}")
		raise typer.Exit(1)

	server_command, server_cwd, server_env = None, None, None
	web_command, web_cwd, web_env = None, None, None

	# Create a dev-instance lock in the web root to prevent concurrent runs
	lock_path = lock_path_for_web_root(web_root)
	try:
		ensure_web_lock(lock_path, owner="cli")
	except RuntimeError as e:
		console.log(f"❌ {e}")
		raise typer.Exit(1) from None

	# In dev, provide a stable PULSE_SECRET persisted in a git-ignored .pulse/secret file
	dev_secret: str | None = None
	if app_instance.mode != "prod":
		dev_secret = os.environ.get("PULSE_SECRET") or None
		if not dev_secret:
			try:
				# Prefer the web root for the .pulse folder when available, otherwise the app file directory
				secret_root = Path(app_file).parent
				secret_dir = Path(secret_root) / ".pulse"
				secret_file = secret_dir / "secret"

				# Ensure .pulse is present and git-ignored
				try:
					secret_dir.mkdir(parents=True, exist_ok=True)
				except Exception:
					pass
				try:
					gi_path = Path(secret_root) / ".gitignore"
					pattern = "\n.pulse/\n"
					content = ""
					if gi_path.exists():
						try:
							content = gi_path.read_text()
						except Exception:
							content = ""
						if ".pulse/" not in content.split():
							gi_path.write_text(content + pattern)
					else:
						gi_path.write_text(pattern.lstrip("\n"))
				except Exception:
					# Non-fatal
					pass

				# Load or create the secret value
				if secret_file.exists():
					try:
						dev_secret = secret_file.read_text().strip() or None
					except Exception:
						dev_secret = None
				if not dev_secret:
					import secrets as _secrets

					dev_secret = _secrets.token_urlsafe(32)
					try:
						secret_file.write_text(dev_secret)
					except Exception:
						# Best effort; env will still carry the secret for this session
						pass
			except Exception:
				dev_secret = None

	if not web_only:
		module_name = parsed["module_name"]
		app_var = parsed["app_var"]
		app_import_string = f"{module_name}:{app_var}.asgi_factory"

		server_command = [
			sys.executable,
			"-m",
			"uvicorn",
			app_import_string,
			"--host",
			address,
			"--port",
			str(port),
			"--factory",
		]
		# Enable hot reload only when not explicitly disabled and not in prod mode
		if reload and app_instance.mode != "prod":
			server_command.append("--reload")
			# Also reload on CSS changes and watch both the app directory and the web root
			server_command.extend(["--reload-include", "*.css"])
			try:
				# Prefer the directory containing the app file (what users edit most)
				app_dir = getattr(env, "pulse_app_dir", None) or os.getcwd()
				server_command.extend(["--reload-dir", str(Path(app_dir))])
				print("Reload dir:", app_dir)
				if web_root.exists():
					server_command.extend(["--reload-dir", str(web_root)])
			except Exception:
				# Best effort; uvicorn will still reload on .py changes
				pass

		# Production runtime optimizations (unopinionated)
		if app_instance.mode == "prod":
			# Prefer uvloop/http tools automatically if installed
			try:
				__import__("uvloop")  # runtime check only
				server_command.extend(["--loop", "uvloop"])
			except Exception:
				pass
			try:
				__import__("httptools")
				server_command.extend(["--http", "httptools"])
			except Exception:
				pass

		server_cwd = parsed["server_cwd"] or Path(
			getattr(env, "pulse_app_dir", os.getcwd())
		)
		server_env = os.environ.copy()
		server_env.update(
			{
				"FORCE_COLOR": "1",
				"PYTHONUNBUFFERED": "1",
				# Signal that the CLI manages the dev lock lifecycle
				ENV_PULSE_LOCK_MANAGED_BY_CLI: "1",
				# Communicate bind host/port to the server for dev codegen
				ENV_PULSE_HOST: address,
				ENV_PULSE_PORT: str(port),
			}
		)
		# In prod when running backend only, disable codegen inside the server
		if app_instance.mode == "prod" and server_only:
			server_env[ENV_PULSE_DISABLE_CODEGEN] = "1"
		if dev_secret:
			server_env[ENV_PULSE_SECRET] = dev_secret

	if not server_only:
		# Resolve and install JS dependencies required by React components
		try:
			components = registered_react_components()

			# Collect version constraints per package name
			constraints: dict[str, list[str | None]] = {
				"pulse-ui-client": [PULSE_PY_VERSION],
			}
			for comp in components:
				# Component base package (from src)
				spec = parse_install_spec(comp.src)
				if spec:
					name_only, ver = parse_dependency_spec(spec)
					constraints.setdefault(name_only, []).append(ver)
					# Explicit component version kwarg is an additional constraint for the same package
					if comp.version:
						constraints.setdefault(name_only, []).append(comp.version)
				# Also consider any extra import statements declared on the component
				for imp in comp.extra_imports:
					try:
						spec2 = parse_install_spec(imp.src)
						if spec2:
							name_only2, ver2 = parse_dependency_spec(spec2)
							constraints.setdefault(name_only2, []).append(ver2)
					except ValueError as ve:
						console.log(f"❌ {ve}")
						raise typer.Exit(1) from None

			# Resolve and materialize install list
			try:
				resolved = resolve_versions(constraints)
			except VersionConflict as e:
				console.log(f"❌ {e}")
				raise typer.Exit(1) from None

			# Build desired install map from resolved versions and RR defaults
			desired: dict[str, str | None] = dict(resolved)
			for rr in [
				"react-router",
				"@react-router/node",
				"@react-router/serve",
				"@react-router/dev",
			]:
				desired.setdefault(rr, "^7")

			# Load existing package.json
			pkg_json = load_package_json(web_root)

			to_add: list[str] = []
			for name, req_ver in sorted(desired.items()):
				# Always pin pulse-ui-client to Python version
				if name == "pulse-ui-client":
					req_ver = PULSE_PY_VERSION

				existing = get_pkg_spec(pkg_json, name)
				if existing is None:
					# Not present -> add with requested version (if any)
					to_add.append(f"{name}@{req_ver}" if req_ver else name)
					continue

				if is_workspace_spec(existing):
					# User-managed
					continue

				# If existing satisfies requested version, no action; else bump
				if spec_satisfies(req_ver, existing):
					continue
				to_add.append(f"{name}@{req_ver}" if req_ver else name)

			# If we have additions/updates, run bun add; else run bun i
			if to_add:
				cmd = ["bun", "add", *to_add]
				console.log(
					f"📦 Adding/updating web dependencies in {web_root} -> {' '.join(cmd)}"
				)
				try:
					subprocess.run(cmd, cwd=web_root, check=True)
				except subprocess.CalledProcessError:
					console.log("❌ Failed to add/update web dependencies with Bun.")
					raise typer.Exit(1) from None
			else:
				# Ensure lock/node_modules are up-to-date
				try:
					subprocess.run(["bun", "i"], cwd=web_root, check=True)
				except subprocess.CalledProcessError:
					console.log("❌ Failed to install web dependencies with Bun.")
					raise typer.Exit(1) from None
		except ValueError as e:
			console.log(f"❌ {e}")
			raise typer.Exit(1) from None

		web_command = ["bun", "run", "dev"]
		web_cwd = web_root
		web_env = os.environ.copy()
		web_env.update(
			{
				"FORCE_COLOR": "1",
				"PYTHONUNBUFFERED": "1",
				# Keep web env consistent as child tools may also look at this
				ENV_PULSE_LOCK_MANAGED_BY_CLI: "1",
			}
		)

	# Pass the extra flags to the web command if it's web only, else pass it to
	# the server (if running both or server-only)
	extra_flags = ctx.args
	if extra_flags:
		if web_only and web_command:
			web_command.extend(extra_flags)
		elif server_command:
			server_command.extend(extra_flags)

	def run_with_pty():
		"""Run server and web processes with PTY-based interleaved output."""
		import fcntl
		import select
		import signal

		colors = {
			"server": "cyan",
			"web": "orange1",
		}

		procs: list[tuple[str, int, int]] = []

		try:
			if server_command:
				pid, fd = pty_module.fork()
				if pid == 0:
					if server_cwd:
						os.chdir(server_cwd)
					env = server_env or os.environ.copy()
					os.execvpe(server_command[0], server_command, env)
				else:
					fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
					procs.append(("server", pid, fd))

			if web_command:
				pid, fd = pty_module.fork()
				if pid == 0:
					if web_cwd:
						os.chdir(web_cwd)
					env = web_env or os.environ.copy()
					os.execvpe(web_command[0], web_command, env)
				else:
					fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
					procs.append(("web", pid, fd))

			fds = {fd: tag for tag, pid, fd in procs}
			buffers = {fd: b"" for fd in fds}

			while procs:
				for tag, pid, fd in list(procs):
					try:
						wpid, status = os.waitpid(pid, os.WNOHANG)
						if wpid == pid:
							procs.remove((tag, pid, fd))
							try:
								os.close(fd)
							except Exception:
								pass
					except ChildProcessError:
						procs.remove((tag, pid, fd))
						try:
							os.close(fd)
						except Exception:
							pass

				if not procs:
					break

				readable_fds = [fd for _, _, fd in procs]
				try:
					ready, _, _ = select.select(readable_fds, [], [], 0.1)
				except (OSError, ValueError):
					break

				for fd in ready:
					try:
						data = os.read(fd, 4096)
						if not data:
							continue

						tag = fds[fd]
						color = colors[tag]
						buffers[fd] += data

						while b"\n" in buffers[fd]:
							line, buffers[fd] = buffers[fd].split(b"\n", 1)
							decoded = line.decode(errors="replace")
							if decoded:
								sys.stdout.write(
									f"\033[{('36' if color == 'cyan' else '38;5;208')}m[{tag}]\033[0m {decoded}\n"
								)
								sys.stdout.flush()
					except OSError:
						continue

			exit_codes = []
			for _tag, pid, fd in procs:
				try:
					_, status = os.waitpid(pid, 0)
					exit_codes.append(
						os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
					)
				except Exception:
					pass
				try:
					os.close(fd)
				except Exception:
					pass

			return max(exit_codes) if exit_codes else 0

		except KeyboardInterrupt:
			for _tag, pid, _fd in procs:
				try:
					os.kill(pid, signal.SIGTERM)
				except Exception:
					pass
			return 130
		finally:
			for _tag, pid, fd in procs:
				try:
					os.kill(pid, signal.SIGKILL)
				except Exception:
					pass
				try:
					os.close(fd)
				except Exception:
					pass

	try:
		code = run_with_pty()
		raise typer.Exit(code)
	finally:
		remove_web_lock(lock_path)


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

	# Validate and set mode based on flags
	mode_flags = [
		name for flag, name in [(dev, "dev"), (ci, "ci"), (prod, "prod")] if flag
	]
	if len(mode_flags) > 1:
		typer.echo("❌ Please specify only one of --dev, --ci, or --prod.")
		raise typer.Exit(1)
	if len(mode_flags) == 1:
		env.pulse_mode = cast(PulseMode, mode_flags[0])

	console.log(f"📁 Loading routes from: {app_file}")
	# Ensure codegen isn't disabled for generate
	env.codegen_disabled = False
	app = load_app_from_target(app_file)
	console.log(f"📋 Found {len(app.routes.flat_tree)} routes")

	addr = app.server_address or "localhost:8000"
	app.run_codegen(addr)

	if len(app.routes.flat_tree) > 0:
		console.log(f"✅ Generated {len(app.routes.flat_tree)} routes successfully!")
	else:
		console.log("⚠️  No routes found to generate")


def main():
	"""Main CLI entry point."""
	try:
		cli()
	except Exception:
		console = Console()
		console.print_exception()
		raise typer.Exit(1) from None


if __name__ == "__main__":
	main()
