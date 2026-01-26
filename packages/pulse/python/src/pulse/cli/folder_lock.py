"""
Folder lock management.

Provides a FolderLock context manager that coordinates across processes and
Uvicorn reloads using environment variables.

Example: prevent multiple Pulse dev instances per web root.
"""

import json
import os
import platform
import socket
import time
from pathlib import Path
from types import TracebackType
from typing import Any

from pulse.cli.helpers import ensure_gitignore_has


def is_process_alive(pid: int) -> bool:
	"""Check if a process with the given PID is running."""
	try:
		# On POSIX, signal 0 checks for existence without killing
		os.kill(pid, 0)
	except ProcessLookupError:
		return False
	except PermissionError:
		# Process exists but we may not have permission
		return True
	except Exception:
		# Best-effort: assume alive if uncertain
		return True
	return True


def _read_lock(lock_path: Path) -> dict[str, Any] | None:
	"""Read and parse lock file contents."""
	try:
		data = json.loads(lock_path.read_text())
		if isinstance(data, dict):
			return data
	except Exception:
		return None
	return None


def _write_gitignore_for_lock(lock_path: Path) -> None:
	"""Add lock file to .gitignore if not already present."""

	ensure_gitignore_has(lock_path.parent, lock_path.name)


def _create_lock_file(lock_path: Path, *, address: str, port: int) -> None:
	"""Create a lock file with current process information."""
	lock_path = Path(lock_path)
	_write_gitignore_for_lock(lock_path)

	if lock_path.exists():
		info = _read_lock(lock_path) or {}
		pid = int(info.get("pid", 0) or 0)
		if pid and is_process_alive(pid):
			existing_addr = info.get("address", address)
			existing_port = info.get("port", port)
			protocol = (
				"http" if existing_addr in ("127.0.0.1", "localhost") else "https"
			)
			url = f"{protocol}://{existing_addr}:{existing_port}"
			raise RuntimeError(
				f"Another Pulse dev instance is running at {url} (pid={pid})"
			)
		# Stale lock; continue to overwrite

	payload: dict[str, Any] = {
		"pid": os.getpid(),
		"created_at": int(time.time()),
		"hostname": socket.gethostname(),
		"platform": platform.platform(),
		"python": platform.python_version(),
		"cwd": os.getcwd(),
		"address": address,
		"port": port,
	}
	try:
		lock_path.parent.mkdir(parents=True, exist_ok=True)
		lock_path.write_text(json.dumps(payload))
	except Exception as exc:
		raise RuntimeError(f"Failed to create lock file at {lock_path}: {exc}") from exc


def _remove_lock_file(lock_path: Path) -> None:
	"""Remove lock file (best-effort)."""
	try:
		Path(lock_path).unlink(missing_ok=True)
	except Exception:
		# Best-effort cleanup
		pass


def lock_path_for_web_root(web_root: Path, filename: str = ".pulse/lock") -> Path:
	"""Return the lock file path for a given web root."""
	return Path(web_root) / filename


class FolderLock:
	"""
	Context manager for folder lock management.

	Coordinates across processes and Uvicorn reloads using environment variables.
	The process that creates the lock (typically the CLI) sets PULSE_LOCK_OWNER.
	Child processes (uvicorn workers, reloaded processes) inherit this env var
	and know not to delete the lock on exit.

	Example:
	    with FolderLock(web_root, address="localhost", port=8000):
	        # Protected region
	        pass
	"""

	def __init__(
		self,
		web_root: Path,
		*,
		address: str,
		port: int,
		filename: str = ".pulse/lock",
	):
		"""
		Initialize FolderLock.

		Args:
		    web_root: Path to the web root directory
		    address: Server address to store in lock file
		    port: Server port to store in lock file
		    filename: Name of the lock file (default: ".pulse/lock")
		"""
		self.lock_path: Path = lock_path_for_web_root(web_root, filename)
		self.address: str = address
		self.port: int = port

	def __enter__(self):
		_create_lock_file(self.lock_path, address=self.address, port=self.port)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: TracebackType | None,
	) -> bool:
		_remove_lock_file(self.lock_path)
		return False
