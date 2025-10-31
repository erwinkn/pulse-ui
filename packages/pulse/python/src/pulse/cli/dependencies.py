from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pulse.cli.packages import (
	VersionConflict,
	get_pkg_spec,
	is_workspace_spec,
	load_package_json,
	parse_dependency_spec,
	parse_install_spec,
	resolve_versions,
	spec_satisfies,
)
from pulse.react_component import ReactComponent, registered_react_components


def convert_pep440_to_semver(python_version: str) -> str:
	"""Convert PEP 440 version format to NPM semver format.

	PEP 440 formats:
	- 0.1.37a1 -> 0.1.37-alpha.1
	- 0.1.37b1 -> 0.1.37-beta.1
	- 0.1.37rc1 -> 0.1.37-rc.1
	- 0.1.37.dev1 -> 0.1.37-dev.1

	Non-pre-release versions are returned unchanged.
	"""
	# Match pre-release patterns: version followed by a/b/rc/dev + number
	# PEP 440: a1, b1, rc1, dev1, alpha1, beta1, etc.
	pattern = r"^(\d+\.\d+\.\d+)([a-z]+)(\d+)$"
	match = re.match(pattern, python_version)

	if match:
		base_version = match.group(1)
		prerelease_type = match.group(2)
		prerelease_num = match.group(3)

		# Map PEP 440 prerelease types to NPM semver
		type_map = {
			"a": "alpha",
			"alpha": "alpha",
			"b": "beta",
			"beta": "beta",
			"rc": "rc",
			"c": "rc",  # PEP 440 also allows 'c' for release candidate
			"dev": "dev",
		}

		npm_type = type_map.get(prerelease_type.lower(), prerelease_type)
		return f"{base_version}-{npm_type}.{prerelease_num}"

	# Also handle .dev format (e.g., 0.1.37.dev1)
	pattern2 = r"^(\d+\.\d+\.\d+)\.dev(\d+)$"
	match2 = re.match(pattern2, python_version)
	if match2:
		base_version = match2.group(1)
		dev_num = match2.group(2)
		return f"{base_version}-dev.{dev_num}"

	# No pre-release, return as-is
	return python_version


class DependencyError(RuntimeError):
	"""Base error for dependency preparation failures."""


class DependencyResolutionError(DependencyError):
	"""Raised when component constraints cannot be resolved."""


class DependencyCommandError(DependencyError):
	"""Raised when Bun commands fail to run."""


@dataclass
class DependencyPlan:
	"""Return value describing the command required to sync dependencies."""

	command: list[str]
	to_add: Sequence[str]


def get_required_dependencies(
	web_root: Path,
	*,
	pulse_version: str,
	component_provider: Callable[
		[], Iterable[ReactComponent[Any]]
	] = registered_react_components,
) -> dict[str, str | None]:
	"""Get the required dependencies for a Pulse app."""
	if not web_root.exists():
		raise DependencyError(f"Directory not found: {web_root}")

	try:
		components = list(component_provider())
	except Exception as exc:
		raise DependencyError("Unable to inspect registered React components") from exc

	constraints: dict[str, list[str | None]] = {
		"pulse-ui-client": [pulse_version],
	}

	for comp in components:
		src = getattr(comp, "src", None)
		component_pkg_name: str | None = None
		if src:
			try:
				spec = parse_install_spec(src)
			except ValueError as exc:
				raise DependencyError(str(exc)) from None
			if spec:
				name_only, ver = parse_dependency_spec(spec)
				constraints.setdefault(name_only, []).append(ver)
				component_pkg_name = name_only

		comp_version = getattr(comp, "version", None)
		if comp_version and component_pkg_name:
			constraints.setdefault(component_pkg_name, []).append(comp_version)

		for extra in getattr(comp, "extra_imports", []):
			extra_src = getattr(extra, "src", None) if extra is not None else None
			if not extra_src:
				continue
			try:
				spec2 = parse_install_spec(extra_src)
			except ValueError as exc:
				raise DependencyError(str(exc)) from None
			if spec2:
				name_only2, ver2 = parse_dependency_spec(spec2)
				constraints.setdefault(name_only2, []).append(ver2)

	try:
		resolved = resolve_versions(constraints)
	except VersionConflict as exc:
		raise DependencyResolutionError(str(exc)) from None

	desired: dict[str, str | None] = dict(resolved)
	for pkg in [
		"react-router",
		"@react-router/node",
		"@react-router/serve",
		"@react-router/dev",
	]:
		desired.setdefault(pkg, "^7")

	return desired


def check_web_dependencies(
	web_root: Path,
	*,
	pulse_version: str,
	component_provider: Callable[
		[], Iterable[ReactComponent[Any]]
	] = registered_react_components,
) -> list[str]:
	"""Check if web dependencies are in sync and return list of packages that need to be added/updated."""
	desired = get_required_dependencies(
		web_root=web_root,
		pulse_version=pulse_version,
		component_provider=component_provider,
	)
	pkg_json = load_package_json(web_root)

	to_add: list[str] = []
	for name, req_ver in sorted(desired.items()):
		effective = req_ver
		if name == "pulse-ui-client":
			effective = convert_pep440_to_semver(pulse_version)

		existing = get_pkg_spec(pkg_json, name)
		if existing is None:
			to_add.append(f"{name}@{effective}" if effective else name)
			continue

		if is_workspace_spec(existing):
			continue

		if spec_satisfies(effective, existing):
			continue

		to_add.append(f"{name}@{effective}" if effective else name)

	return to_add


def prepare_web_dependencies(
	web_root: Path,
	*,
	pulse_version: str,
	component_provider: Callable[
		[], Iterable[ReactComponent[Any]]
	] = registered_react_components,
) -> DependencyPlan | None:
	"""Inspect registered components and return the Bun command needed to sync dependencies."""
	to_add = check_web_dependencies(
		web_root=web_root,
		pulse_version=pulse_version,
		component_provider=component_provider,
	)

	if to_add:
		return DependencyPlan(command=["bun", "add", *to_add], to_add=to_add)

	return DependencyPlan(command=["bun", "i"], to_add=())
