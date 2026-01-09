#!/usr/bin/env python3
"""Find available tasks in PRD - tasks ready to work on."""

import json
import sys
from pathlib import Path


def load_prd(path: str) -> dict:
	with open(path) as f:
		return json.load(f)


def get_available_tasks(features: list[dict]) -> list[dict]:
	"""Return tasks that are ready to work on.

	A task is available if:
	- passes is False (not yet completed)
	- has no dependencies, OR all dependencies have passes: true
	"""
	# Build lookup for passes status
	passes_map = {f["id"]: f.get("passes", False) for f in features}

	available = []
	for f in features:
		if f.get("passes", False):
			continue  # Already done

		deps = f.get("dependencies", [])
		deps_satisfied = all(passes_map.get(dep, False) for dep in deps)

		if deps_satisfied:
			available.append(f)

	# Sort by priority (lower = higher priority)
	return sorted(available, key=lambda f: (f["priority"], f["id"]))


def main(prd_path: str = "prd.json") -> int:
	path = Path(prd_path)
	if not path.exists():
		print(f"ERROR: {prd_path} not found")
		return 1

	prd = load_prd(prd_path)
	features = prd.get("features", [])

	if not features:
		print("No features in PRD")
		return 0

	# Count stats
	total = len(features)
	done = sum(1 for f in features if f.get("passes", False))
	available = get_available_tasks(features)

	print(f"Progress: {done}/{total} complete\n")

	if not available:
		if done == total:
			print("ALL TASKS COMPLETE")
		else:
			print("No tasks available (blocked by dependencies)")
			print("\nBlocked tasks:")
			for f in features:
				if not f.get("passes", False):
					deps = f.get("dependencies", [])
					passes_map = {ft["id"]: ft.get("passes", False) for ft in features}
					blocking = [d for d in deps if not passes_map.get(d, False)]
					print(f"  {f['id']}: blocked by {', '.join(blocking)}")
		return 0

	print(f"Available tasks ({len(available)}):\n")
	for f in available:
		deps = f.get("dependencies", [])
		dep_str = f" [after: {', '.join(deps)}]" if deps else ""
		print(f"  [{f['priority']}] {f['id']}: {f['title']}{dep_str}")
	return 0


if __name__ == "__main__":
	path = sys.argv[1] if len(sys.argv) > 1 else "prd.json"
	sys.exit(main(path))
