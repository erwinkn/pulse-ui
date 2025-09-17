"""
Command-line interface for Pulse UI.
This module provides the CLI commands for running the server and generating routes.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from pulse.env import (
    ENV_PULSE_DISABLE_CODEGEN,
    ENV_PULSE_LOCK_MANAGED_BY_CLI,
    ENV_PULSE_SECRET,
    env,
)
from pulse.helpers import (
    ensure_web_lock,
    lock_path_for_web_root,
    remove_web_lock,
)

from .helpers import (
    find_available_port,
    install_hints_for_mkcert,
    load_app_from_target,
    parse_app_target,
)
from .terminal import PulseTerminalViewer

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
        "127.0.0.1",
        "--bind-address",
        help="Host uvicorn binds to",
    ),
    port: int = typer.Option(8000, "--bind-port", help="Port uvicorn binds to"),
    # Mode flags
    dev: bool = typer.Option(False, "--dev", help="Run in development mode"),
    ci: bool = typer.Option(False, "--ci", help="Run in CI mode"),
    prod: bool = typer.Option(False, "--prod", help="Run in production mode"),
    # Subdomain production convenience
    subdomains: bool = typer.Option(
        False,
        "--subdomains/--no-subdomains",
        help="Run web and server on two subdomains (app and api). Requires --prod.",
    ),
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
        env.pulse_mode = mode_flags[0]  # type: ignore

    if subdomains and not prod:
        typer.echo(
            "❌ --subdomains requires --prod (to enable prod cookie/CORS behavior)."
        )
        raise typer.Exit(1)
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
        raise typer.Exit(1)

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

        # In prod subdomain mode, require local TLS certs for HTTPS (Secure cookies)
        if subdomains:
            # Locate certs under app .pulse/certs
            secret_root = Path(getattr(env, "pulse_app_dir", os.getcwd()))
            cert_dir = Path(secret_root) / ".pulse" / "certs"
            cert_file = cert_dir / "cert.pem"
            key_file = cert_dir / "key.pem"
            if not (cert_file.exists() and key_file.exists()):
                console = Console()
                console.log("🔐 Generating local TLS certificates for subdomain run...")
                try:
                    cert_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                mkcert_path = shutil.which("mkcert")
                if not mkcert_path:
                    console.log("❌ mkcert not found. Please install it:")
                    for line in install_hints_for_mkcert():
                        console.log(f"  {line}")
                    raise typer.Exit(1)
                # Install local CA (idempotent)
                try:
                    subprocess.run(
                        [mkcert_path, "-install"],
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except Exception:
                    pass
                cmd = [
                    mkcert_path,
                    "-key-file",
                    str(key_file),
                    "-cert-file",
                    str(cert_file),
                    "*.localhost",
                    "localhost",
                    "127.0.0.1",
                    "::1",
                ]
                try:
                    subprocess.run(cmd, check=True)
                except subprocess.CalledProcessError:
                    console.log("❌ Failed to generate certificates with mkcert.")
                    console.log(f"Tried: {' '.join(cmd)}")
                    raise typer.Exit(1)
                if not (cert_file.exists() and key_file.exists()):
                    console.log("❌ Certificate files were not created. Aborting.")
                    raise typer.Exit(1)
            print("cert_file:", cert_file)
            print("key_file:", key_file)
            # server_command.extend(
            #     ["--ssl-certfile", str(cert_file), "--ssl-keyfile", str(key_file)]
            # )

        server_cwd = parsed["server_cwd"] or Path(
            getattr(env, "pulse_app_dir", os.getcwd())
        )
        server_env = os.environ.copy()
        server_env.update(
            {
                "FORCE_COLOR": "1",
                # Signal that the CLI manages the dev lock lifecycle
                ENV_PULSE_LOCK_MANAGED_BY_CLI: "1",
            }
        )
        # In prod when running backend only, disable codegen inside the server
        if app_instance.mode == "prod" and server_only:
            server_env[ENV_PULSE_DISABLE_CODEGEN] = "1"
        if dev_secret:
            server_env[ENV_PULSE_SECRET] = dev_secret

    if not server_only:
        web_command = ["bun", "run", "dev"]
        web_cwd = web_root
        web_env = os.environ.copy()
        web_env.update(
            {
                "FORCE_COLOR": "1",
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

    # In dev, use terminal viewer. In prod/ci, run directly.
    if env.pulse_mode == "dev":
        app = PulseTerminalViewer(
            server_command=server_command,
            server_cwd=server_cwd,
            server_env=server_env,
            web_command=web_command,
            web_cwd=web_cwd,
            web_env=web_env,
        )
        try:
            app.run()
        finally:
            remove_web_lock(lock_path)
    else:
        procs: list[subprocess.Popen] = []
        try:
            if server_command:
                print("Server command:", server_command)
                procs.append(
                    subprocess.Popen(server_command, cwd=server_cwd, env=server_env)
                )
            if web_command:
                procs.append(subprocess.Popen(web_command, cwd=web_cwd, env=web_env))
            # Wait for first to exit, then terminate the other if any
            exit_codes = [p.wait() for p in procs if p is not None]
            code = max(exit_codes) if exit_codes else 0
            raise typer.Exit(code)
        finally:
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
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
        env.pulse_mode = mode_flags[0]  # type: ignore

    console.log(f"📁 Loading routes from: {app_file}")
    # Ensure codegen isn't disabled for generate
    env.codegen_disabled = False
    app = load_app_from_target(app_file)
    console.log(f"📋 Found {len(app.routes.flat_tree)} routes")

    addr = app.server_address or "127.0.0.1:8000"
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
        raise typer.Exit(1)


if __name__ == "__main__":
    main()
