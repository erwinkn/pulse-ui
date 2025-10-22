#!/usr/bin/env python3
"""
Pre-commit hook to sync version numbers from Python packages to JavaScript packages.

This script reads version numbers from pyproject.toml files (source of truth) and
updates the corresponding package.json files to match.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

try:
	import tomllib
except ImportError:
	import tomli as tomllib  # type: ignore


PACKAGE_PAIRS: List[Tuple[str, str]] = [
	(
		"packages/pulse/python/pyproject.toml",
		"packages/pulse/js/package.json",
	),
	(
		"packages/pulse-mantine/python/pyproject.toml",
		"packages/pulse-mantine/js/package.json",
	),
]


def get_version_from_pyproject(pyproject_path: Path) -> str:
	"""Extract version from pyproject.toml file."""
	with open(pyproject_path, "rb") as f:
		data = tomllib.load(f)
	return data["project"]["version"]


def get_version_from_package_json(package_json_path: Path) -> str:
	"""Extract version from package.json file."""
	with open(package_json_path, "r") as f:
		data = json.load(f)
	return data["version"]


def update_package_json_version(package_json_path: Path, version: str) -> None:
	"""Update version in package.json file."""
	with open(package_json_path, "r") as f:
		data = json.load(f)

	data["version"] = version

	with open(package_json_path, "w") as f:
		json.dump(data, f, indent="\t")
		f.write("\n")


def main() -> int:
	"""Main function to sync versions."""
	repo_root = Path(__file__).parent.parent
	changed_files = []
	errors = []

	for pyproject_rel, package_json_rel in PACKAGE_PAIRS:
		pyproject_path = repo_root / pyproject_rel
		package_json_path = repo_root / package_json_rel

		if not pyproject_path.exists():
			errors.append(f"Python package not found: {pyproject_rel}")
			continue

		if not package_json_path.exists():
			errors.append(f"JavaScript package not found: {package_json_rel}")
			continue

		try:
			python_version = get_version_from_pyproject(pyproject_path)
			js_version = get_version_from_package_json(package_json_path)

			if python_version != js_version:
				print(f"Syncing {package_json_rel}: {js_version} -> {python_version}")
				update_package_json_version(package_json_path, python_version)
				changed_files.append(str(package_json_path))
		except Exception as e:
			errors.append(
				f"Error processing {pyproject_rel} -> {package_json_rel}: {e}"
			)

	if errors:
		print("\nErrors occurred during version sync:", file=sys.stderr)
		for error in errors:
			print(f"  - {error}", file=sys.stderr)
		return 1

	if changed_files:
		print("\nVersion sync complete. The following files were updated:")
		for file in changed_files:
			print(f"  - {file}")
		print("\nThese files have been modified and need to be staged.")
		print("Please review the changes and add them to your commit:")
		for file in changed_files:
			print(f"  git add {file}")
		return 1  # Return non-zero to abort commit so user can stage changes

	return 0


if __name__ == "__main__":
	sys.exit(main())
