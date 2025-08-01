"""
Command-line interface for Pulse UI.

This module provides the CLI commands for running the server and generating routes.
"""

import os
import sys
import subprocess
import importlib.util
from pathlib import Path

import typer

from pulse.app import App
from pulse.codegen import generate_all_routes

cli = typer.Typer(
    name="pulse",
    help="Pulse UI - Python to TypeScript bridge with server-side callbacks",
    no_args_is_help=True,
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

    # Clear any existing global routes before loading
    from pulse.app import clear_routes

    clear_routes()

    # Add the file's directory to Python path so imports work
    sys.path.insert(0, str(file_path.parent.absolute()))

    try:
        # Load the module dynamically
        spec = importlib.util.spec_from_file_location("user_app", file_path)
        if spec is None or spec.loader is None:
            typer.echo(f"❌ Could not load module from: {file_path}")
            raise typer.Exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "app"):
            if isinstance(module.app, App):
                app_instance = module.app
                if len(app_instance.routes) == 0:
                    typer.echo(f"⚠️  No routes found in {file_path}")
                    typer.echo("Make sure to define routes using either:")
                    typer.echo(
                        "  1. app = pulse.App() with @app.route() decorators, or"
                    )
                    typer.echo("  2. @pulse.route() decorators + the right imports")
                return app_instance

        typer.echo(f"⚠️  No app found in {file_path}")
        typer.echo("Make sure your file defines an app using app = pulse.App()")
        raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error loading {file_path}: {e}")
        raise typer.Exit(1)
    finally:
        # Clean up sys.path
        if str(file_path.parent.absolute()) in sys.path:
            sys.path.remove(str(file_path.parent.absolute()))


@cli.command("serve")
def serve(
    app_file: str = typer.Argument(..., help="Python file with a pulse.App instance"),
    address: str = typer.Option(
        "localhost",
        "--address",
        help="Address to bind the server to",
    ),
    port: int = typer.Option(8000, "--port", help="Port to bind the server to"),
):
    """Run a Python file with the Pulse server."""
    typer.echo(f"📁 Loading app from: {app_file}")
    app_instance = load_app_from_file(app_file)
    typer.echo(f"📋 Found {len(app_instance.routes)} routes")

    typer.echo(f"🚀 Starting Pulse UI server on {address}:{port}")
    app_instance.run(host=address, port=port)


@cli.command("web")
def web(
    app_file: str = typer.Argument(
        ..., help="Python file with a pulse.App instance to get web_dir from"
    ),
):
    """Start the web development server."""
    app_instance = load_app_from_file(app_file)
    web_dir = Path(app_instance.codegen.web_dir)

    if not web_dir.exists():
        typer.echo(f"❌ Directory not found: {web_dir}")
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


@cli.command("generate")
def generate(
    app_file: str = typer.Argument(..., help="Path to your Python file with routes"),
):
    """Generate TypeScript routes without starting the server."""
    typer.echo("🔄 Generating TypeScript routes...")

    typer.echo(f"📁 Loading routes from: {app_file}")
    app_instance = load_app_from_file(app_file)
    typer.echo(f"📋 Found {len(app_instance.routes)} routes")

    generate_all_routes(app_instance)

    if len(app_instance.routes) > 0:
        typer.echo(f"✅ Generated {len(app_instance.routes)} routes successfully!")
    else:
        typer.echo("✅ Cleaned up old route files")
        typer.echo("⚠️  No routes found to generate")


def main():
    """Main CLI entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        typer.echo("\n👋 Shutting down...")
        raise typer.Exit(0)
    except Exception as e:
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    main()
