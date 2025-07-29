"""
Command-line interface for Pulse UI.

This module provides the CLI commands for running the server and generating routes.
"""

import os
import subprocess
from pathlib import Path

import typer

from pulse.server import start_server
from pulse.codegen import generate_all_routes

app = typer.Typer(
    name="pulse",
    help="Pulse UI - Python to TypeScript bridge with server-side callbacks",
    no_args_is_help=True,
)

# Create a sub-app for run commands
run_app = typer.Typer(name="run", help="Start services (server or web)")
app.add_typer(run_app, name="run")


@run_app.command("server")
def run_server(
    address: str = typer.Option(
        "localhost", "--address", help="Address to bind the server to"
    ),
    port: int = typer.Option(8000, "--port", help="Port to bind the server to"),
):
    """Start the backend server with automatic route generation."""
    typer.echo(f"🚀 Starting Pulse UI server on {address}:{port}")
    start_server(host=address, port=port, auto_generate=True)


@run_app.command("web")
def run_web():
    """Start the web development server (bun dev)."""
    web_dir = Path("pulse-web")

    if not web_dir.exists():
        typer.echo("❌ pulse-web directory not found")
        typer.echo("Make sure you're running this from the project root directory")
        raise typer.Exit(1)

    typer.echo("🌐 Starting web development server...")
    typer.echo(f"📁 Working directory: {web_dir.absolute()}")

    try:
        # Change to the web directory and run bun dev
        os.chdir(web_dir)
        subprocess.run(["bun", "dev"], check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Failed to start web server: {e}")
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo("❌ 'bun' command not found")
        typer.echo("Please install bun: https://bun.sh/")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        typer.echo("\n👋 Web server stopped")


# For backward compatibility: `pulse run` defaults to server
@run_app.callback(invoke_without_command=True)
def run_default(
    ctx: typer.Context,
    address: str = typer.Option(
        "localhost", "--address", help="Address to bind the server to"
    ),
    port: int = typer.Option(8000, "--port", help="Port to bind the server to"),
):
    """Start the backend server (default behavior for 'pulse run')."""
    if ctx.invoked_subcommand is None:
        # No subcommand provided, default to running the server
        typer.echo(f"🚀 Starting Pulse UI server on {address}:{port}")
        start_server(host=address, port=port, auto_generate=True)


@app.command("generate")
def generate():
    """Generate TypeScript routes without starting the server."""
    typer.echo("🔄 Generating TypeScript routes...")
    num_routes = generate_all_routes()

    if num_routes > 0:
        typer.echo(f"✅ Generated {num_routes} routes successfully!")
    else:
        typer.echo("✅ Cleaned up old route files")
        typer.echo("⚠️  No routes found to generate")
        typer.echo("Make sure you have defined routes using @define_route decorator")


def main():
    """Main CLI entry point."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\n👋 Shutting down...")
        raise typer.Exit(0)
    except Exception as e:
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    main()
