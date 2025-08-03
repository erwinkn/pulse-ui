"""
Command-line interface for Pulse UI.
This module provides the CLI commands for running the server and generating routes.
"""

import asyncio
import importlib.util
import os
import pty
import socket
import sys
from pathlib import Path

import typer
from rich.console import Console

from pulse.app import App
from pulse.routing import clear_routes

from textual.app import App as TextualApp, ComposeResult
from textual.containers import Container
from textual.widgets import RichLog
from rich.text import Text

cli = typer.Typer(
    name="pulse",
    help="Pulse UI - Python to TypeScript bridge with server-side callbacks",
    no_args_is_help=True,
)


def find_available_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"Could not find an available port after {max_attempts} attempts starting from {start_port}"
    )


def load_app_from_file(file_path: str | Path) -> App:
    """Load routes from a Python file (supports both App instances and global @ps.route decorators)."""
    file_path = Path(file_path)

    if not file_path.exists():
        typer.echo(f"❌ File not found: {file_path}")
        raise typer.Exit(1)

    if not file_path.suffix == ".py":
        typer.echo(f"❌ File must be a Python file (.py): {file_path}")
        raise typer.Exit(1)

    clear_routes()
    sys.path.insert(0, str(file_path.parent.absolute()))

    try:
        spec = importlib.util.spec_from_file_location("user_app", file_path)
        if spec is None or spec.loader is None:
            typer.echo(f"❌ Could not load module from: {file_path}")
            raise typer.Exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "app") and isinstance(module.app, App):
            app_instance = module.app
            if not app_instance.routes:
                typer.echo(f"⚠️  No routes found in {file_path}")
            return app_instance

        typer.echo(f"⚠️  No app found in {file_path}")
        raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error loading {file_path}: {e}")
        raise typer.Exit(1)
    finally:
        if str(file_path.parent.absolute()) in sys.path:
            sys.path.remove(str(file_path.parent.absolute()))


class Terminal(RichLog):
    """A widget that runs a command in a pseudo-terminal."""

    def __init__(self, command, cwd, env=None, **kwargs):
        super().__init__(highlight=True, markup=True, **kwargs)
        self.command = command
        self.cwd = cwd
        self.env = env
        self.pid = None
        self.fd = None

    async def on_mount(self) -> None:
        """Start the command when the widget is mounted."""
        self.pid, self.fd = pty.fork()

        if self.pid == 0:  # Child process
            os.chdir(self.cwd)
            env = os.environ.copy()
            if self.env:
                env.update(self.env)
            os.execvpe(self.command[0], self.command, env)
        else:  # Parent process
            loop = asyncio.get_running_loop()
            loop.add_reader(self.fd, self.read_from_pty)

    def read_from_pty(self) -> None:
        """Read from the PTY and update the widget."""
        if self.fd is None:
            return
        try:
            data = os.read(self.fd, 1024)
            if not data:
                self.update_log_with_exit_message()
                return
            self.write(Text.from_ansi(data.decode(errors="replace")))
        except OSError:
            self.update_log_with_exit_message()

    def update_log_with_exit_message(self):
        if self.fd:
            asyncio.get_running_loop().remove_reader(self.fd)
            os.close(self.fd)
            self.fd = None
        self.write("\n\n[b red]PROCESS EXITED[/b red]")
        self.border_style = "red"

    async def on_key(self, event) -> None:
        if self.fd:
            if event.key == "ctrl+c":
                os.write(self.fd, b"\x03")
            else:
                os.write(self.fd, event.key.encode())

    def on_unmount(self) -> None:
        """Ensure the process is terminated on unmount."""
        if self.pid:
            try:
                os.kill(self.pid, 9)
            except ProcessLookupError:
                pass


class PulseTerminalViewer(TextualApp):
    """A Textual app to view Pulse server logs in interactive terminals."""

    CSS = """
    Screen {
        background: transparent;
    }
    #main_container {
        layout: horizontal;
        background: transparent;
    }
    Terminal {
        width: 1fr;
        height: 100%;
        margin: 0 1;
        border: round grey;
    }
    Terminal:focus {
        border: round white;
    }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(
        self,
        server_command=None,
        server_cwd=None,
        server_env=None,
        web_command=None,
        web_cwd=None,
        web_env=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.server_command = server_command
        self.server_cwd = server_cwd
        self.server_env = server_env
        self.web_command = web_command
        self.web_cwd = web_cwd
        self.web_env = web_env

    def compose(self) -> ComposeResult:
        with Container(id="main_container"):
            if self.server_command:
                server_term = Terminal(
                    self.server_command,
                    self.server_cwd,
                    self.server_env,
                    id="server_term",
                )
                server_term.border_title = "🐍 Python Server"
                yield server_term

            if self.web_command:
                web_term = Terminal(
                    self.web_command, self.web_cwd, self.web_env, id="web_term"
                )
                web_term.border_title = "🌐 Web Server"
                yield web_term


@cli.command("run")
def run(
    app_file: str = typer.Argument(..., help="Python file with a pulse.App instance"),
    address: str = typer.Option("localhost", "--address"),
    port: int = typer.Option(8000, "--port"),
    server_only: bool = typer.Option(False, "--server-only"),
    web_only: bool = typer.Option(False, "--web-only"),
    no_reload: bool = typer.Option(False, "--no-reload"),
    find_port: bool = typer.Option(True, "--find-port/--no-find-port"),
):
    """Run the Pulse server and web development server together."""
    if server_only and web_only:
        typer.echo("❌ Cannot use --server-only and --web-only at the same time.")
        raise typer.Exit(1)

    if find_port:
        port = find_available_port(port)

    console = Console()
    console.log(f"📁 Loading app from: {app_file}")
    app_instance = load_app_from_file(app_file)
    console.log(f"📋 Found {len(app_instance.routes)} routes")

    web_dir = Path(app_instance.codegen.cfg.web_dir)
    if not web_dir.exists() and not server_only:
        console.log(f"❌ Directory not found: {web_dir}")
        raise typer.Exit(1)

    server_command, server_cwd, server_env = None, None, None
    web_command, web_cwd, web_env = None, None, None

    if not web_only:
        module_name = Path(app_file).stem
        app_import_string = f"{module_name}:app.asgi_factory"
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
        if not no_reload:
            server_command.append("--reload")

        server_cwd = Path(app_file).parent
        server_env = os.environ.copy()
        server_env.update(
            {
                "PULSE_APP_FILE": app_file,
                "PULSE_HOST": address,
                "PULSE_PORT": str(port),
                "PYTHONUNBUFFERED": "1",
                "FORCE_COLOR": "1",
            }
        )

    if not server_only:
        web_command = ["bun", "run", "dev"]
        web_cwd = web_dir
        web_env = os.environ.copy()
        web_env.update({"FORCE_COLOR": "1"})

    app = PulseTerminalViewer(
        server_command=server_command,
        server_cwd=server_cwd,
        server_env=server_env,
        web_command=web_command,
        web_cwd=web_cwd,
        web_env=web_env,
    )
    app.run()


@cli.command("generate")
def generate(
    app_file: str = typer.Argument(..., help="Path to your Python file with routes"),
):
    """Generate TypeScript routes without starting the server."""
    console = Console()
    console.log("🔄 Generating TypeScript routes...")

    console.log(f"📁 Loading routes from: {app_file}")
    app = load_app_from_file(app_file)
    console.log(f"📋 Found {len(app.routes)} routes")

    app.run_codegen()

    if len(app.routes) > 0:
        console.log(f"✅ Generated {len(app.routes)} routes successfully!")
    else:
        console.log("⚠️  No routes found to generate")


def main():
    """Main CLI entry point."""
    try:
        cli()
    except Exception as e:
        console = Console()
        console.log(f"❌ Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    main()
