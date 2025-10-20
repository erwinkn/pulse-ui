"""
Pulse Mantine package version indicator.

Exposes `__version__` which matches the distribution version when installed.
Falls back to reading local pyproject.toml during editable/dev usage.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

__all__ = ["__version__"]


def _read_local_pyproject_version() -> str | None:
	try:
		here = Path(__file__).resolve()
		root = here.parent.parent  # pulse_mantine/version.py -> pulse_mantine/
		# project pyproject.toml is two levels up: packages/pulse-mantine/python/pyproject.toml
		pyproject = root.parent.parent / "pyproject.toml"
		if not pyproject.exists():
			return None
		for line in pyproject.read_text().splitlines():
			line = line.strip()
			if line.startswith("version") and "=" in line:
				_, rhs = line.split("=", 1)
				rhs = rhs.strip().strip("\"'")
				if rhs:
					return rhs
		return None
	except Exception:
		return None


def _resolve_version() -> str:
	try:
		return _pkg_version("pulse-mantine")
	except PackageNotFoundError:
		pass
	local = _read_local_pyproject_version()
	if local:
		return local
	return "0.0.0"


__version__: str = _resolve_version()
