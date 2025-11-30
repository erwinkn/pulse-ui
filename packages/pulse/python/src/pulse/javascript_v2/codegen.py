"""Codegen: collect dependencies and produce ordered JS output.

This module takes the global registries of JsImport and JsFunction objects
and produces an ordered list of definitions to emit in the generated JS.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from dataclasses import dataclass, field

from pulse.codegen.imports import IMPORT_REGISTRY, Import
from pulse.javascript_v2.constants import const_to_js
from pulse.javascript_v2.function import FUNCTION_CACHE, AnyJsFunction
from pulse.javascript_v2.nodes import JSExpr, JSImport


@dataclass
class ConstantDef:
	"""A constant definition to emit."""

	name: str
	value: JSExpr
	# The original Python value's id for deduplication
	value_id: int


@dataclass
class FunctionDef:
	"""A function definition to emit."""

	name: str
	js_function: "AnyJsFunction"


@dataclass
class CodegenOutput:
	"""The ordered output for JS code generation."""

	imports: list[JSImport] = field(default_factory=list)
	constants: list[ConstantDef] = field(default_factory=list)
	functions: list[FunctionDef] = field(default_factory=list)
	# Maps function qualified name -> emitted function name
	function_registry: dict[str, str] = field(default_factory=dict)


def _get_function_id(fn: "AnyJsFunction") -> str:
	"""Get a unique identifier for a JsFunction."""
	underlying = fn.fn
	module = underlying.__module__
	qualname = underlying.__qualname__
	return f"{module}.{qualname}"


def _topological_sort(functions: list["AnyJsFunction"]) -> list["AnyJsFunction"]:
	"""Topologically sort functions by their dependencies.

	Dependencies must come before dependents in the output.
	Handles cycles by detecting them (mutual recursion is allowed
	since functions are hoisted in JS, but we still want a reasonable order).
	"""
	# Build adjacency: fn -> set of fn deps
	fn_to_deps: dict[int, set[int]] = {}

	for js_fn in functions:
		deps: set[int] = set()
		for value in js_fn.globals.values():
			if isinstance(value, Import):
				continue
			if inspect.isfunction(value) and value in FUNCTION_CACHE:
				deps.add(id(FUNCTION_CACHE[value]))
		fn_to_deps[id(js_fn)] = deps

	# Kahn's algorithm
	id_to_fn = {id(fn): fn for fn in functions}
	in_degree: dict[int, int] = defaultdict(int)

	for fn_id in fn_to_deps:
		if fn_id not in in_degree:
			in_degree[fn_id] = 0
		for dep_id in fn_to_deps[fn_id]:
			if dep_id in id_to_fn:  # Only count deps in our set
				in_degree[fn_id] += 1

	# Start with nodes that have no dependencies
	queue = [fn_id for fn_id, degree in in_degree.items() if degree == 0]
	result: list["AnyJsFunction"] = []
	visited: set[int] = set()

	while queue:
		fn_id = queue.pop(0)
		if fn_id in visited:
			continue
		visited.add(fn_id)
		result.append(id_to_fn[fn_id])

		# Decrement in-degree for dependents
		for other_id, deps in fn_to_deps.items():
			if fn_id in deps and other_id not in visited:
				in_degree[other_id] -= 1
				if in_degree[other_id] <= 0:
					queue.append(other_id)

	# Handle any remaining (cycles) - just append in original order
	for fn in functions:
		if id(fn) not in visited:
			result.append(fn)

	return result


def _merge_imports(imports: list[Import]) -> list[JSImport]:
	"""Merge Import objects into JSImport nodes, combining same-source imports."""
	# Group by source
	by_source: dict[str, list[Import]] = defaultdict(list)
	for imp in imports:
		by_source[imp.src].append(imp)

	result: list[JSImport] = []
	for src, imps in by_source.items():
		default_name: str | None = None
		named: list[str | tuple[str, str]] = []

		for imp in imps:
			if imp.is_default:
				if default_name is None:
					default_name = imp.name
				# If multiple defaults from same source, keep first (or could error)
			else:
				named.append(imp.name)

		result.append(JSImport(src=src, default=default_name, named=named))

	return result


def _collect_constants(
	functions: list["AnyJsFunction"],
) -> tuple[list[ConstantDef], dict[int, str]]:
	"""Collect and deduplicate constants from all functions.

	Returns:
		- List of ConstantDef to emit
		- Mapping from value id -> constant name (for use during transpilation)
	"""
	# Track by identity to dedupe - use first encountered name
	seen: dict[int, ConstantDef] = {}

	for js_fn in functions:
		for name, value in js_fn.globals.items():
			# Skip non-constants
			if (
				isinstance(value, Import)
				or inspect.isfunction(value)
				or inspect.ismodule(value)
				or callable(value)
			):
				continue

			value_id = id(value)
			if value_id not in seen:
				seen[value_id] = ConstantDef(
					name=name,
					value=const_to_js(value),  # pyright: ignore[reportArgumentType]
					value_id=value_id,
				)

	id_to_name = {c.value_id: c.name for c in seen.values()}
	return list(seen.values()), id_to_name


def _collect_imports_from_functions(
	functions: list["AnyJsFunction"],
) -> list[Import]:
	"""Collect all Import dependencies from functions."""
	seen: set[int] = set()
	result: list[Import] = []

	for js_fn in functions:
		for value in js_fn.globals.values():
			if isinstance(value, Import):
				if id(value) not in seen:
					seen.add(id(value))
					result.append(value)

	return result


def collect_from_functions(entry_functions: list["AnyJsFunction"]) -> CodegenOutput:
	"""Collect all definitions needed for the given entry functions.

	This traverses the dependency graph starting from the entry functions
	and collects all imports, constants, and function definitions needed.

	Args:
		entry_functions: The "root" functions to start from.

	Returns:
		CodegenOutput with ordered definitions ready to emit.
	"""
	# Collect all reachable functions via BFS
	all_functions: dict[int, "AnyJsFunction"] = {}
	queue = list(entry_functions)

	while queue:
		js_fn = queue.pop(0)
		fn_id = id(js_fn)
		if fn_id in all_functions:
			continue
		all_functions[fn_id] = js_fn

		# Add dependencies to queue
		for value in js_fn.globals.values():
			if inspect.isfunction(value) and value in FUNCTION_CACHE:
				dep_fn = FUNCTION_CACHE[value]
				if id(dep_fn) not in all_functions:
					queue.append(dep_fn)

	functions_list = list(all_functions.values())

	# Topologically sort
	sorted_functions = _topological_sort(functions_list)

	# Collect imports from functions
	func_imports = _collect_imports_from_functions(sorted_functions)
	merged_imports = _merge_imports(func_imports)

	# Collect constants
	constants, _const_id_to_name = _collect_constants(sorted_functions)

	# Build function definitions and registry
	function_defs: list[FunctionDef] = []
	function_registry: dict[str, str] = {}

	for js_fn in sorted_functions:
		fn_id = _get_function_id(js_fn)
		fn_name = js_fn.fn.__name__
		function_defs.append(FunctionDef(name=fn_name, js_function=js_fn))
		function_registry[fn_id] = fn_name

	return CodegenOutput(
		imports=merged_imports,
		constants=constants,
		functions=function_defs,
		function_registry=function_registry,
	)


def collect_from_registries() -> CodegenOutput:
	"""Collect all definitions from the global registries.

	This uses all registered functions and imports to produce
	the complete output.

	Returns:
		CodegenOutput with all registered definitions.
	"""

	all_functions = list(FUNCTION_CACHE.values())
	all_plain_imports = list(IMPORT_REGISTRY)

	if not all_functions:
		# Just plain imports, no functions
		merged_imports = _merge_imports(all_plain_imports)
		return CodegenOutput(imports=merged_imports)

	output = collect_from_functions(all_functions)

	# Also include any plain imports that weren't referenced by functions
	func_import_ids = {
		id(imp) for fn in all_functions for imp in fn.get_import_deps().values()
	}
	extra_imports = [imp for imp in all_plain_imports if id(imp) not in func_import_ids]

	if extra_imports:
		extra_merged = _merge_imports(extra_imports)
		output.imports.extend(extra_merged)

	return output
