#!/usr/bin/env python3
"""
Bump package version and sync everything.

Usage:
    python scripts/bump_version.py <package-name> [--patch | --minor | --major | --alpha | --beta | --rc | --version <version>]

Examples:
    python scripts/bump_version.py pulse                    # patch bump (default)
    python scripts/bump_version.py pulse --patch            # patch bump (explicit)
    python scripts/bump_version.py pulse --minor            # minor bump
    python scripts/bump_version.py pulse --major            # major bump
    python scripts/bump_version.py pulse --alpha            # alpha bump (0.1.44 -> 0.1.45a1, 0.1.45a1 -> 0.1.45a2)
    python scripts/bump_version.py pulse --beta             # beta bump (0.1.45a2 -> 0.1.45b1, 0.1.45b1 -> 0.1.45b2)
    python scripts/bump_version.py pulse --rc               # rc bump (0.1.45b2 -> 0.1.45rc1, 0.1.45rc1 -> 0.1.45rc2)
    python scripts/bump_version.py pulse --version 0.2.5    # exact version
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

# Map package names to their pyproject.toml paths
PACKAGE_PATHS = {
	"pulse": "packages/pulse/python/pyproject.toml",
	"pulse-mantine": "packages/pulse-mantine/python/pyproject.toml",
	"pulse-recharts": "packages/pulse-recharts/pyproject.toml",
	"pulse-msal": "packages/pulse-msal/pyproject.toml",
	"pulse-lucide": "packages/pulse-lucide/pyproject.toml",
	"pulse-aws": "packages/pulse-aws/pyproject.toml",
	"pulse-ag-grid": "packages/pulse-ag-grid/pyproject.toml",
}

# Packages that have corresponding JS packages
PACKAGE_PAIRS: list[tuple[str, str]] = [
	(
		"packages/pulse/python/pyproject.toml",
		"packages/pulse/js/package.json",
	),
	(
		"packages/pulse-mantine/python/pyproject.toml",
		"packages/pulse-mantine/js/package.json",
	),
]


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


def get_version_from_pyproject(pyproject_path: Path) -> str:
	"""Extract version from pyproject.toml file."""
	with open(pyproject_path, "rb") as f:
		data = tomllib.load(f)
	return data["project"]["version"]


def bump_patch(version: str) -> str:
	"""Bump patch version (e.g., 0.1.44 -> 0.1.45)."""
	# Strip any pre-release suffixes for bumping
	base_version = re.match(r"^(\d+\.\d+\.\d+)", version)
	if not base_version:
		raise ValueError(f"Invalid version format: {version}")

	parts = base_version.group(1).split(".")
	parts[2] = str(int(parts[2]) + 1)
	return ".".join(parts)


def bump_minor(version: str) -> str:
	"""Bump minor version (e.g., 0.1.44 -> 0.2.0)."""
	base_version = re.match(r"^(\d+\.\d+\.\d+)", version)
	if not base_version:
		raise ValueError(f"Invalid version format: {version}")

	parts = base_version.group(1).split(".")
	parts[1] = str(int(parts[1]) + 1)
	parts[2] = "0"
	return ".".join(parts)


def bump_major(version: str) -> str:
	"""Bump major version (e.g., 0.1.44 -> 1.0.0)."""
	base_version = re.match(r"^(\d+\.\d+\.\d+)", version)
	if not base_version:
		raise ValueError(f"Invalid version format: {version}")

	parts = base_version.group(1).split(".")
	parts[0] = str(int(parts[0]) + 1)
	parts[1] = "0"
	parts[2] = "0"
	return ".".join(parts)


def bump_alpha(version: str) -> str:
	"""Bump alpha version (e.g., 0.1.44 -> 0.1.45a1, 0.1.45a1 -> 0.1.45a2)."""
	# Check if already an alpha version
	alpha_match = re.match(r"^(\d+\.\d+\.\d+)a(\d+)$", version)
	if alpha_match:
		base = alpha_match.group(1)
		num = int(alpha_match.group(2)) + 1
		return f"{base}a{num}"

	# Not an alpha - bump patch and start at a1
	base_version = re.match(r"^(\d+\.\d+\.\d+)", version)
	if not base_version:
		raise ValueError(f"Invalid version format: {version}")

	parts = base_version.group(1).split(".")
	parts[2] = str(int(parts[2]) + 1)
	return ".".join(parts) + "a1"


def bump_beta(version: str) -> str:
	"""Bump beta version (e.g., 0.1.45a2 -> 0.1.45b1, 0.1.45b1 -> 0.1.45b2)."""
	# Check if already a beta version
	beta_match = re.match(r"^(\d+\.\d+\.\d+)b(\d+)$", version)
	if beta_match:
		base = beta_match.group(1)
		num = int(beta_match.group(2)) + 1
		return f"{base}b{num}"

	# Extract base version (handles alpha, or plain version)
	base_version = re.match(r"^(\d+\.\d+\.\d+)", version)
	if not base_version:
		raise ValueError(f"Invalid version format: {version}")

	return f"{base_version.group(1)}b1"


def bump_rc(version: str) -> str:
	"""Bump rc version (e.g., 0.1.45b2 -> 0.1.45rc1, 0.1.45rc1 -> 0.1.45rc2)."""
	# Check if already an rc version
	rc_match = re.match(r"^(\d+\.\d+\.\d+)rc(\d+)$", version)
	if rc_match:
		base = rc_match.group(1)
		num = int(rc_match.group(2)) + 1
		return f"{base}rc{num}"

	# Extract base version (handles alpha, beta, or plain version)
	base_version = re.match(r"^(\d+\.\d+\.\d+)", version)
	if not base_version:
		raise ValueError(f"Invalid version format: {version}")

	return f"{base_version.group(1)}rc1"


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


def update_pyproject_version(pyproject_path: Path, new_version: str) -> None:
	"""Update version in pyproject.toml file."""
	content = pyproject_path.read_text()

	# Match version = "x.y.z" pattern
	pattern = r'(version\s*=\s*["\'])([^"\']+)(["\'])'

	def replace_version(match: re.Match[str]) -> str:
		return f"{match.group(1)}{new_version}{match.group(3)}"

	new_content = re.sub(pattern, replace_version, content)

	if new_content == content:
		raise ValueError(f"Could not find version line in {pyproject_path}")

	pyproject_path.write_text(new_content)
	print(f"Updated {pyproject_path}: version -> {new_version}")


def sync_js_versions(repo_root: Path) -> None:
	"""Sync version numbers from Python packages to JavaScript packages."""
	changed_files: list[str] = []
	errors: list[str] = []

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
			semver_version = convert_pep440_to_semver(python_version)
			js_version = get_version_from_package_json(package_json_path)

			if semver_version != js_version:
				print(f"Syncing {package_json_rel}: {js_version} -> {semver_version}")
				update_package_json_version(package_json_path, semver_version)
				changed_files.append(str(package_json_path))
		except Exception as e:
			errors.append(
				f"Error processing {pyproject_rel} -> {package_json_rel}: {e}"
			)

	if errors:
		error_msg = "\nErrors occurred during version sync:\n" + "\n".join(
			f"  - {e}" for e in errors
		)
		raise RuntimeError(error_msg)

	if changed_files:
		print(f"\nSynced {len(changed_files)} JavaScript package(s)")


def run_command(cmd: list[str], cwd: Path | None = None) -> None:
	"""Run a command and check for errors."""
	print(f"Running: {' '.join(cmd)}")
	result = subprocess.run(cmd, cwd=cwd, check=False)
	if result.returncode != 0:
		raise RuntimeError(
			f"Command failed with exit code {result.returncode}: {' '.join(cmd)}"
		)


def main() -> int:
	"""Main function."""
	if len(sys.argv) < 2:
		print(
			"Usage: python scripts/bump_version.py <package-name> [--patch | --minor | --major | --alpha | --beta | --rc | --version <version>]",
			file=sys.stderr,
		)
		print("\nAvailable packages:", file=sys.stderr)
		for pkg in sorted(PACKAGE_PATHS.keys()):
			print(f"  - {pkg}", file=sys.stderr)
		return 1

	package_name = sys.argv[1]

	if package_name not in PACKAGE_PATHS:
		print(f"Unknown package: {package_name}", file=sys.stderr)
		print("\nAvailable packages:", file=sys.stderr)
		for pkg in sorted(PACKAGE_PATHS.keys()):
			print(f"  - {pkg}", file=sys.stderr)
		return 1

	# Parse flags
	bump_type: str | None = None
	exact_version: str | None = None

	args = sys.argv[2:]
	i = 0
	while i < len(args):
		if args[i] == "--major":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			bump_type = "major"
		elif args[i] == "--minor":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			bump_type = "minor"
		elif args[i] == "--patch":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			bump_type = "patch"
		elif args[i] == "--alpha":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			bump_type = "alpha"
		elif args[i] == "--beta":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			bump_type = "beta"
		elif args[i] == "--rc":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			bump_type = "rc"
		elif args[i] == "--version":
			if bump_type is not None or exact_version is not None:
				print("Error: Cannot specify multiple bump types", file=sys.stderr)
				return 1
			if i + 1 >= len(args):
				print("Error: --version requires a version argument", file=sys.stderr)
				return 1
			exact_version = args[i + 1]
			i += 1
		else:
			print(f"Error: Unknown argument: {args[i]}", file=sys.stderr)
			return 1
		i += 1

	repo_root = Path(__file__).parent.parent
	pyproject_path = repo_root / PACKAGE_PATHS[package_name]

	if not pyproject_path.exists():
		print(f"Package file not found: {pyproject_path}", file=sys.stderr)
		return 1

	try:
		# Get current version and calculate new version
		current_version = get_version_from_pyproject(pyproject_path)

		if exact_version:
			new_version = exact_version
		elif bump_type == "major":
			new_version = bump_major(current_version)
		elif bump_type == "minor":
			new_version = bump_minor(current_version)
		elif bump_type == "alpha":
			new_version = bump_alpha(current_version)
		elif bump_type == "beta":
			new_version = bump_beta(current_version)
		elif bump_type == "rc":
			new_version = bump_rc(current_version)
		else:
			# Default to patch bump (also handles explicit --patch)
			new_version = bump_patch(current_version)

		# Step 1: Update pyproject.toml version
		print(f"Bumping {package_name}: {current_version} -> {new_version}")
		update_pyproject_version(pyproject_path, new_version)

		# Step 2: Sync JS versions if applicable
		print("\nSyncing JavaScript package versions...")
		sync_js_versions(repo_root)

		# Step 3: Update lock files
		print("\nUpdating Python lock file...")
		run_command(["uv", "sync", "--all-packages", "--dev"], cwd=repo_root)

		print("\nUpdating JavaScript lock file...")
		run_command(["bun", "i"], cwd=repo_root)

		print(f"\n✓ Successfully bumped {package_name} to {new_version}")
		print("Don't forget to commit the changes!")
		return 0

	except Exception as e:
		print(f"\n✗ Error: {e}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
