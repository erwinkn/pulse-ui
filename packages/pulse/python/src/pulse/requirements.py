from __future__ import annotations

from collections.abc import Mapping

_REQUIREMENTS: list[tuple[str, str]] = []


def add_requirement(name: str, version: str) -> None:
	if not name or not version:
		return
	_REQUIREMENTS.append((name, version))


def register_requirements(packages: Mapping[str, str]) -> None:
	for name, version in packages.items():
		if not name or not version:
			continue
		add_requirement(name, version)


def get_requirements() -> list[tuple[str, str]]:
	return list(_REQUIREMENTS)


def clear_requirements() -> None:
	_REQUIREMENTS.clear()


def require(packages: Mapping[str, str]) -> None:
	"""Register npm package version requirements for dependency syncing."""
	if not isinstance(packages, Mapping):
		raise TypeError("require expects a mapping of package names to versions")
	if not packages:
		return

	normalized: dict[str, str] = {}
	for name, version in packages.items():
		if not isinstance(name, str) or not name.strip():
			raise TypeError("require expects non-empty package names")
		if not isinstance(version, str) or not version.strip():
			raise TypeError(f"require expects a version string for {name!r}")
		normalized[name.strip()] = version.strip()

	register_requirements(normalized)


__all__ = ["require"]
