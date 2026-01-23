#!/usr/bin/env python3
"""
Check or bump packages that changed since their last version bump.

Usage:
    python scripts/version_audit.py check [--all]
    python scripts/version_audit.py bump [--patch|--minor|--major|--alpha|--beta|--rc|--version X.Y.Z] [--dry-run]
"""

import argparse
import subprocess
import sys
from pathlib import Path

PACKAGE_CONFIG: list[tuple[str, str, list[str]]] = [
	("pulse", "packages/pulse/python/pyproject.toml", ["packages/pulse"]),
	(
		"pulse-mantine",
		"packages/pulse-mantine/python/pyproject.toml",
		["packages/pulse-mantine"],
	),
	(
		"pulse-recharts",
		"packages/pulse-recharts/pyproject.toml",
		["packages/pulse-recharts"],
	),
	(
		"pulse-lucide",
		"packages/pulse-lucide/pyproject.toml",
		["packages/pulse-lucide"],
	),
	(
		"pulse-ag-grid",
		"packages/pulse-ag-grid/pyproject.toml",
		["packages/pulse-ag-grid"],
	),
	("pulse-msal", "packages/pulse-msal/pyproject.toml", ["packages/pulse-msal"]),
	("pulse-aws", "packages/pulse-aws/pyproject.toml", ["packages/pulse-aws"]),
]


def run_git(args: list[str], cwd: Path) -> str:
	result = subprocess.run(
		["git", *args],
		cwd=cwd,
		check=False,
		capture_output=True,
		text=True,
	)
	if result.returncode != 0:
		msg = result.stderr.strip() or "git command failed"
		raise RuntimeError(f"git {' '.join(args)}: {msg}")
	return result.stdout.strip()


def run_command(args: list[str], cwd: Path) -> None:
	result = subprocess.run(args, cwd=cwd, check=False)
	if result.returncode != 0:
		raise RuntimeError(
			f"command failed with exit code {result.returncode}: {' '.join(args)}"
		)


def get_changes(
	repo_root: Path, version_file: Path, package_dirs: list[Path]
) -> tuple[str, list[str]]:
	if not version_file.exists():
		raise RuntimeError(f"missing version file: {version_file}")
	last_commit = run_git(
		["log", "-1", "--format=%H", "--", str(version_file)], repo_root
	)
	if not last_commit:
		raise RuntimeError(f"no git history for: {version_file}")
	last_info = run_git(
		["log", "-1", "--date=short", "--format=%ad %h %s", "--", str(version_file)],
		repo_root,
	)
	diff_args = ["diff", "--name-only", f"{last_commit}..HEAD", "--"]
	for path in package_dirs:
		diff_args.append(str(path))
	changed = run_git(diff_args, repo_root)
	files = [line for line in changed.splitlines() if line]
	return last_info, files


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	subparsers = parser.add_subparsers(dest="command", required=True)

	check_parser = subparsers.add_parser("check", help="check for changes")
	check_parser.add_argument(
		"--all", action="store_true", help="show packages with no changes"
	)

	bump_parser = subparsers.add_parser("bump", help="bump changed packages")
	group = bump_parser.add_mutually_exclusive_group()
	group.add_argument("--major", action="store_true")
	group.add_argument("--minor", action="store_true")
	group.add_argument("--patch", action="store_true")
	group.add_argument("--alpha", action="store_true")
	group.add_argument("--beta", action="store_true")
	group.add_argument("--rc", action="store_true")
	group.add_argument("--version")
	bump_parser.add_argument("--dry-run", action="store_true")

	return parser.parse_args()


def main() -> int:
	args = parse_args()
	repo_root = Path(__file__).parent.parent
	changed_packages: list[str] = []
	results: list[tuple[str, str, list[str]]] = []

	for name, version_rel, dir_rels in PACKAGE_CONFIG:
		version_file = repo_root / version_rel
		package_dirs = [repo_root / rel for rel in dir_rels]
		last_info, files = get_changes(repo_root, version_file, package_dirs)
		results.append((name, last_info, files))
		if files:
			changed_packages.append(name)

	if args.command == "check":
		for name, last_info, files in results:
			if files:
				print(f"{name}: changed since {last_info}")
				for file in files:
					print(f"  - {file}")
			elif args.all:
				print(f"{name}: clean (last bump {last_info})")
		if changed_packages:
			print(f"\n{len(changed_packages)} package(s) need a bump")
			return 1
		print("All packages clean")
		return 0

	bump_args: list[str] = []
	if args.version:
		bump_args = ["--version", args.version]
	elif args.major:
		bump_args = ["--major"]
	elif args.minor:
		bump_args = ["--minor"]
	elif args.patch:
		bump_args = ["--patch"]
	elif args.alpha:
		bump_args = ["--alpha"]
	elif args.beta:
		bump_args = ["--beta"]
	elif args.rc:
		bump_args = ["--rc"]
	else:
		bump_args = ["--patch"]

	if not changed_packages:
		print("No packages to bump")
		return 0

	for name in changed_packages:
		cmd = ["make", "bump", f"PKG={name}"]
		if bump_args:
			cmd.append(f"ARGS={' '.join(bump_args)}")
		if args.dry_run:
			print(" ".join(cmd))
			continue
		run_command(cmd, repo_root)

	return 0


if __name__ == "__main__":
	sys.exit(main())
