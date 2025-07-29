"""
Command-line interface for Pulse UI.

This module provides the CLI commands for running the server and generating routes.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .server import start_server
from .codegen import generate_all_routes


def cmd_run(args):
    """Run the Pulse UI server with automatic route generation."""

    print(f"🚀 Starting Pulse UI server on {args.address}:{args.port}")
    start_server(host=args.address, port=args.port, auto_generate=True)


def cmd_generate(args):
    """Generate TypeScript route files from Python definitions."""
    print("🔄 Generating TypeScript routes...")
    num_routes = generate_all_routes()

    if num_routes > 0:
        print(f"✅ Generated {num_routes} routes successfully!")
    else:
        print("✅ Cleaned up old route files")
        print("⚠️  No routes found to generate")
        print("Make sure you have defined routes using @define_route decorator")


def cmd_run_web(args):
    """Start the web development server using bun dev."""
    web_dir = Path("pulse-web")

    if not web_dir.exists():
        print("❌ pulse-web directory not found")
        print("Make sure you're running this from the project root directory")
        sys.exit(1)

    print("🌐 Starting web development server...")
    print(f"📁 Working directory: {web_dir.absolute()}")

    try:
        # Change to the web directory and run bun dev
        os.chdir(web_dir)
        subprocess.run(["bun", "dev"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start web server: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ 'bun' command not found")
        print("Please install bun: https://bun.sh/")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Web server stopped")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="pulse",
        description="Pulse UI - Python to TypeScript bridge with server-side callbacks",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Start services (server or web)")
    run_subparsers = run_parser.add_subparsers(
        dest="run_command", help="Run subcommands"
    )

    # Run server subcommand
    run_server_parser = run_subparsers.add_parser(
        "server", help="Start the backend server with automatic route generation"
    )
    run_server_parser.add_argument(
        "--address",
        default="localhost",
        help="Address to bind the server to (default: localhost)",
    )
    run_server_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )
    run_server_parser.set_defaults(func=cmd_run)

    # Run web subcommand
    run_web_parser = run_subparsers.add_parser(
        "web", help="Start the web development server (bun dev)"
    )
    run_web_parser.set_defaults(func=cmd_run_web)

    # For backward compatibility, also accept `pulse run` without subcommand as server
    run_parser.add_argument(
        "--address",
        default="localhost",
        help="Address to bind the server to (default: localhost)",
    )
    run_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )
    run_parser.set_defaults(func=cmd_run, run_command=None)

    # Generate command
    generate_parser = subparsers.add_parser(
        "generate", help="Generate TypeScript routes without starting the server"
    )
    generate_parser.set_defaults(func=cmd_generate)

    # Parse arguments
    args = parser.parse_args()

    # Show help if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle run command specially to check for subcommands
    if args.command == "run" and hasattr(args, "run_command"):
        if args.run_command == "web":
            args.func = cmd_run_web
        elif args.run_command == "server" or args.run_command is None:
            args.func = cmd_run
        else:
            print(f"Unknown run subcommand: {args.run_command}")
            run_parser.print_help()
            sys.exit(1)

    # Execute the command
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
