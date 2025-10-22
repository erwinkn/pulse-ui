import importlib
import importlib.util
import platform
import socket
import sys
from pathlib import Path
from typing import Literal, TypedDict

import typer
from rich.console import Console

from pulse.app import App
from pulse.env import env


def os_family() -> Literal["windows", "mac", "linux"]:
	s = platform.system().lower()
	if "windows" in s:
		return "windows"
	if "darwin" in s or "mac" in s:
		return "mac"
	return "linux"


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


class ParsedAppTarget(TypedDict):
	mode: Literal["path", "module"]
	module_name: str
	app_var: str
	file_path: Path | None
	server_cwd: Path | None


def _module_path_from_file(file_path: Path) -> tuple[str, Path]:
	"""Compute the module import path for a file within a package hierarchy.
	Returns (module_path, server_cwd). server_cwd is the directory that should be
	used as the working directory so that importing module_path works.
	"""
	file_path = file_path.resolve()
	is_init = file_path.name == "__init__.py"
	parts: list[str] = [] if is_init else [file_path.stem]
	current = file_path.parent
	# Default to the file's parent when not inside a package
	top_package_parent = current
	while (current / "__init__.py").exists():
		parts.insert(0, current.name)
		top_package_parent = current.parent
		current = current.parent
	module_path = ".".join(parts)
	server_cwd = top_package_parent
	return module_path, server_cwd


def parse_app_target(target: str) -> ParsedAppTarget:
	"""Parse an app target which can be either:
	- a filesystem path to a Python file with optional ":var" (default var is "app"), e.g. "examples/main.py:app"
	- a module path in uvicorn style with a required ":var", e.g. "examples.main:app"

	Returns a dict describing how to import/run it.
	"""
	# Split optional ":var" specifier once from the right
	# Handle Windows drive letters by checking if the colon is followed by a path separator
	if ":" in target:
		# Check if this looks like a Windows drive letter (e.g., "C:\path" or "C:/path")
		colon_pos = target.rfind(":")
		if colon_pos > 0 and colon_pos < len(target) - 1:
			char_after_colon = target[colon_pos + 1]
			if char_after_colon in ["\\", "/"]:
				# This is a Windows drive letter, not a variable specifier
				path_or_module, app_var = target, "app"
			else:
				# This is a variable specifier
				path_or_module, app_var = target.rsplit(":", 1)
				app_var = app_var or "app"
		else:
			# Single colon at end, treat as variable specifier
			path_or_module, app_var = target.rsplit(":", 1)
			app_var = app_var or "app"
	else:
		path_or_module, app_var = target, "app"

	p = Path(path_or_module)
	if p.exists():
		if p.is_dir():
			# If a package directory is passed, try __init__.py semantics by using the directory name as module
			init_file = p / "__init__.py"
			if init_file.exists():
				module_name, server_cwd = _module_path_from_file(init_file)
				file_path = init_file
			else:
				module_name = p.name
				file_path = None
				server_cwd = p.parent.resolve()
		else:
			file_path = p.resolve()
			module_name, server_cwd = _module_path_from_file(file_path)
		return {
			"mode": "path",
			"module_name": module_name,
			"app_var": app_var,
			"file_path": file_path,
			"server_cwd": server_cwd,
		}

	# Treat as module import path
	module_name = path_or_module
	return {
		"mode": "module",
		"module_name": module_name,
		"app_var": app_var,
		"file_path": None,
		"server_cwd": None,
	}


def load_app_from_file(file_path: str | Path) -> App:
	"""Load routes from a Python file (supports both App instances and global @ps.route decorators)."""
	file_path = Path(file_path)

	if not file_path.exists():
		typer.echo(f"❌ File not found: {file_path}")
		raise typer.Exit(1)

	if not file_path.suffix == ".py":
		typer.echo(f"❌ File must be a Python file (.py): {file_path}")
		raise typer.Exit(1)

	# Set env so downstream codegen can resolve paths relative to the app file
	env.pulse_app_file = str(file_path.absolute())
	env.pulse_app_dir = str(file_path.parent.absolute())

	# clear_routes()
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

	except Exception:
		console = Console()
		console.log(f"❌ Error loading {file_path}")
		console.print_exception()
		raise typer.Exit(1) from None
	finally:
		if str(file_path.parent.absolute()) in sys.path:
			sys.path.remove(str(file_path.parent.absolute()))


def load_app_from_target(target: str) -> App:
	"""Load an App instance from either a file path (with optional :var) or a module path (uvicorn style)."""
	parsed = parse_app_target(target)

	# Set env for downstream codegen resolution
	if parsed["mode"] == "path":
		file_path = parsed["file_path"]
		if file_path is None:
			typer.echo(f"❌ Could not determine a Python file from: {target}")
			raise typer.Exit(1)
		env.pulse_app_file = str(file_path.absolute())
		env.pulse_app_dir = str(file_path.parent.absolute())

		sys.path.insert(0, str(file_path.parent.absolute()))
		try:
			spec = importlib.util.spec_from_file_location(
				parsed["module_name"], file_path
			)
			if spec is None or spec.loader is None:
				typer.echo(f"❌ Could not load module from: {file_path}")
				raise typer.Exit(1)
			module = importlib.util.module_from_spec(spec)
			sys.modules[spec.name] = module
			spec.loader.exec_module(module)
		except Exception:
			console = Console()
			console.log(f"❌ Error loading {file_path}")
			console.print_exception()
			raise typer.Exit(1) from None
		finally:
			if str(file_path.parent.absolute()) in sys.path:
				sys.path.remove(str(file_path.parent.absolute()))

	else:
		# module mode
		try:
			module = importlib.import_module(parsed["module_name"])  # type: ignore[name-defined]
		except Exception:
			console = Console()
			console.log(f"❌ Error importing module: {parsed['module_name']}")
			console.print_exception()
			raise typer.Exit(1) from None

		# Try to set env paths from the resolved module file
		file_attr = getattr(module, "__file__", None)
		if file_attr:
			fp = Path(file_attr)
			env.pulse_app_file = str(fp.absolute())
			env.pulse_app_dir = str(fp.parent.absolute())

	# Fetch the app attribute
	var_name = parsed["app_var"]
	if not hasattr(module, var_name):
		typer.echo(f"❌ App variable '{var_name}' not found in {parsed['module_name']}")
		raise typer.Exit(1)
	app_candidate = getattr(module, var_name)
	if not isinstance(app_candidate, App):
		typer.echo(
			f"❌ '{var_name}' in {parsed['module_name']} is not a pulse.App instance"
		)
		raise typer.Exit(1)
	if not app_candidate.routes:
		typer.echo("⚠️  No routes found")
	return app_candidate


def install_hints_for_mkcert() -> list[str]:
	fam = os_family()
	if fam == "mac":
		return [
			"brew install mkcert nss",
			"mkcert -install",
		]
	if fam == "windows":
		return [
			"choco install mkcert    # or: winget install FiloSottile.mkcert",
			"mkcert -install",
		]
	return [
		"sudo apt install -y mkcert libnss3-tools    # Debian/Ubuntu",
		"# or: sudo dnf install -y mkcert nss-tools   # Fedora",
		"# or: sudo pacman -Syu mkcert nss           # Arch",
		"mkcert -install",
	]
