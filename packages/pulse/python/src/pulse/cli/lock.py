"""
CLI lock management.

Provides typed helpers for coordinating exclusive access to a Pulse web root.
"""

from __future__ import annotations

import json
import os
import platform as platform_module
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from pulse.cli.helpers import ensure_gitignore_has

DEFAULT_LOCK_FILENAME = ".pulse/lock"


@dataclass(frozen=True, slots=True)
class LockInfo:
	pid: int
	created_at: int
	hostname: str
	platform: str
	python: str
	cwd: str
	address: str
	port: int

	@property
	def url(self) -> str:
		protocol = "http" if self.address in ("127.0.0.1", "localhost") else "https"
		return f"{protocol}://{self.address}:{self.port}"

	def to_payload(self) -> dict[str, int | str]:
		return {
			"pid": self.pid,
			"created_at": self.created_at,
			"hostname": self.hostname,
			"platform": self.platform,
			"python": self.python,
			"cwd": self.cwd,
			"address": self.address,
			"port": self.port,
		}

	@classmethod
	def current(cls, *, address: str, port: int) -> LockInfo:
		return cls(
			pid=os.getpid(),
			created_at=int(time.time()),
			hostname=socket.gethostname(),
			platform=platform_module.platform(),
			python=platform_module.python_version(),
			cwd=os.getcwd(),
			address=address,
			port=port,
		)

	@classmethod
	def from_payload(cls, payload: object) -> LockInfo | None:
		if not isinstance(payload, dict):
			return None

		data: dict[str, object] = payload
		pid = _coerce_int(data.get("pid"))
		created_at = _coerce_int(data.get("created_at"))
		port = _coerce_int(data.get("port"))
		hostname = data.get("hostname")
		platform_name = data.get("platform")
		python = data.get("python")
		cwd = data.get("cwd")
		address = data.get("address")
		if (
			pid is None
			or created_at is None
			or port is None
			or not isinstance(hostname, str)
			or not isinstance(platform_name, str)
			or not isinstance(python, str)
			or not isinstance(cwd, str)
			or not isinstance(address, str)
		):
			return None

		return cls(
			pid=pid,
			created_at=created_at,
			hostname=hostname,
			platform=platform_name,
			python=python,
			cwd=cwd,
			address=address,
			port=port,
		)


def _coerce_int(value: object) -> int | None:
	if isinstance(value, bool):
		return None
	if isinstance(value, int):
		return value
	if isinstance(value, str):
		try:
			return int(value)
		except ValueError:
			return None
	return None


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


def read_lock_info(lock_path: Path) -> LockInfo | None:
	"""Read and parse lock file contents."""
	try:
		return LockInfo.from_payload(json.loads(lock_path.read_text()))
	except Exception:
		return None


def active_lock_info(lock_path: Path) -> LockInfo | None:
	"""Return lock info when it belongs to a live process."""
	info = read_lock_info(lock_path)
	if info is None:
		return None

	if info.pid <= 0 or not is_process_alive(info.pid):
		return None
	return info


def _write_gitignore_for_lock(lock_path: Path) -> None:
	"""Add lock file to .gitignore if not already present."""

	ensure_gitignore_has(lock_path.parent, lock_path.name)


def write_lock_info(lock_path: Path, info: LockInfo) -> None:
	lock_path = Path(lock_path)
	_write_gitignore_for_lock(lock_path)
	lock_path.parent.mkdir(parents=True, exist_ok=True)
	lock_path.write_text(json.dumps(info.to_payload()))


def create_lock(lock_path: Path, *, address: str, port: int) -> LockInfo:
	"""Create a lock file with current process information."""
	lock_path = Path(lock_path)
	if info := active_lock_info(lock_path):
		raise RuntimeError(
			f"Another Pulse dev instance is running at {info.url} (pid={info.pid})"
		)

	info = LockInfo.current(address=address, port=port)
	try:
		write_lock_info(lock_path, info)
	except Exception as exc:
		raise RuntimeError(f"Failed to create lock file at {lock_path}: {exc}") from exc
	return info


def remove_lock(lock_path: Path) -> None:
	"""Remove lock file (best-effort)."""
	try:
		Path(lock_path).unlink(missing_ok=True)
	except Exception:
		# Best-effort cleanup
		pass


def lock_path_for_web_root(
	web_root: Path, filename: str = DEFAULT_LOCK_FILENAME
) -> Path:
	"""Return the lock file path for a given web root."""
	return Path(web_root) / filename


class FolderLock:
	"""
	Context manager for a web-root lock file.
	"""

	def __init__(
		self,
		web_root: Path,
		*,
		address: str,
		port: int,
		filename: str = DEFAULT_LOCK_FILENAME,
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
		create_lock(self.lock_path, address=self.address, port=self.port)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: TracebackType | None,
	) -> bool:
		remove_lock(self.lock_path)
		return False
