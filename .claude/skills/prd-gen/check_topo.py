#!/usr/bin/env python3
"""Validate topological order of PRD dependency graph."""

import json
import sys
from collections import defaultdict
from pathlib import Path


def load_prd(path: str) -> dict:
	with open(path) as f:
		return json.load(f)


def build_graph(features: list[dict]) -> tuple[dict[str, set[str]], dict[str, int]]:
	"""Build adjacency list and priority map from features."""
	# id -> set of ids that depend on it (outgoing edges)
	graph: dict[str, set[str]] = defaultdict(set)
	# id -> priority
	priorities: dict[str, int] = {}

	all_ids = {f["id"] for f in features}

	for f in features:
		fid = f["id"]
		priorities[fid] = f["priority"]
		graph[fid]  # ensure node exists

		for dep in f.get("dependencies", []):
			if dep not in all_ids:
				print(f"ERROR: {fid} depends on unknown feature {dep}")
				sys.exit(1)
			graph[dep].add(fid)  # dep -> fid (fid depends on dep)

	return dict(graph), priorities


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
	"""Find all cycles using DFS."""
	WHITE, GRAY, BLACK = 0, 1, 2
	color = {node: WHITE for node in graph}
	cycles = []

	def dfs(node: str, path: list[str]) -> None:
		color[node] = GRAY
		path.append(node)

		for neighbor in graph.get(node, set()):
			if color[neighbor] == GRAY:
				# Found cycle - extract it
				cycle_start = path.index(neighbor)
				cycles.append(path[cycle_start:] + [neighbor])
			elif color[neighbor] == WHITE:
				dfs(neighbor, path)

		path.pop()
		color[node] = BLACK

	for node in graph:
		if color[node] == WHITE:
			dfs(node, [])

	return cycles


def check_priority_order(
	graph: dict[str, set[str]], priorities: dict[str, int]
) -> list[tuple[str, str, int, int]]:
	"""Check that dependencies have lower priority (run first) than dependents."""
	violations = []

	for dep, dependents in graph.items():
		dep_priority = priorities[dep]
		for dependent in dependents:
			dependent_priority = priorities[dependent]
			# Dependent should have higher priority number (runs later)
			if dependent_priority <= dep_priority:
				violations.append((dep, dependent, dep_priority, dependent_priority))

	return violations


def find_components(graph: dict[str, set[str]]) -> list[set[str]]:
	"""Find connected components (treating edges as undirected)."""
	# Build undirected adjacency
	undirected: dict[str, set[str]] = defaultdict(set)
	for node, neighbors in graph.items():
		undirected[node]  # ensure exists
		for n in neighbors:
			undirected[node].add(n)
			undirected[n].add(node)

	visited: set[str] = set()
	components: list[set[str]] = []

	def bfs(start: str) -> set[str]:
		component = {start}
		queue = [start]
		while queue:
			node = queue.pop(0)
			for neighbor in undirected[node]:
				if neighbor not in component:
					component.add(neighbor)
					queue.append(neighbor)
		return component

	for node in undirected:
		if node not in visited:
			comp = bfs(node)
			visited |= comp
			components.append(comp)

	return components


def topo_sort(graph: dict[str, set[str]]) -> list[str]:
	"""Kahn's algorithm for topological sort."""
	# Count incoming edges
	in_degree: dict[str, int] = {node: 0 for node in graph}
	for neighbors in graph.values():
		for n in neighbors:
			in_degree[n] = in_degree.get(n, 0) + 1

	# Start with nodes that have no dependencies
	queue = [n for n, d in in_degree.items() if d == 0]
	result = []

	while queue:
		queue.sort()  # deterministic order
		node = queue.pop(0)
		result.append(node)
		for neighbor in graph.get(node, set()):
			in_degree[neighbor] -= 1
			if in_degree[neighbor] == 0:
				queue.append(neighbor)

	return result


def main(prd_path: str = "prd.json") -> int:
	path = Path(prd_path)
	if not path.exists():
		print(f"ERROR: {prd_path} not found")
		return 1

	prd = load_prd(prd_path)
	features = prd.get("features", [])

	if not features:
		print("WARNING: No features in PRD")
		return 0

	print(f"Checking {len(features)} features...\n")

	graph, priorities = build_graph(features)

	# Check for cycles
	cycles = find_cycles(graph)
	if cycles:
		print("ERROR: Dependency cycles detected:")
		for cycle in cycles:
			print(f"  {' -> '.join(cycle)}")
		return 1
	print("OK: No cycles")

	# Check priority ordering
	violations = check_priority_order(graph, priorities)
	if violations:
		print("\nERROR: Priority violations (dependency must have lower priority):")
		for dep, dependent, dep_pri, dependent_pri in violations:
			print(f"  {dep} (pri={dep_pri}) <- {dependent} (pri={dependent_pri})")
			print(
				f"    {dependent} depends on {dep}, but {dependent}.priority <= {dep}.priority"
			)
		return 1
	print("OK: Priority order respects dependencies")

	# Show components
	components = find_components(graph)
	print(f"\nFound {len(components)} component(s):")
	for i, comp in enumerate(
		sorted(components, key=lambda c: min(priorities[n] for n in c))
	):
		sorted_nodes = sorted(comp, key=lambda n: priorities[n])
		print(f"  Component {i + 1}: {', '.join(sorted_nodes)}")

	# Show topological order
	topo = topo_sort(graph)
	print(f"\nTopological order: {' -> '.join(topo)}")

	# Show execution order by priority
	by_priority = sorted(features, key=lambda f: (f["priority"], f["id"]))
	print("\nExecution order (by priority):")
	for f in by_priority:
		deps = f.get("dependencies", [])
		dep_str = f" [depends: {', '.join(deps)}]" if deps else ""
		status = "PASS" if f["passes"] else "TODO"
		print(f"  {f['priority']:2d}. [{status}] {f['id']}: {f['title']}{dep_str}")

	print("\nOK: All checks passed")
	return 0


if __name__ == "__main__":
	path = sys.argv[1] if len(sys.argv) > 1 else "prd.json"
	sys.exit(main(path))
