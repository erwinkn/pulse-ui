"""Route code generation using the javascript_v2 import system."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from pulse.javascript_v2.constants import JsConstant
from pulse.javascript_v2.function import AnyJsFunction, JsFunction
from pulse.javascript_v2.imports import Import, registered_imports
from pulse.react_component import ReactComponent


def _generate_import_statement(src: str, imports: list[Import]) -> str:
	"""Generate import statement(s) for a source module."""
	default_imports: list[Import] = []
	namespace_imports: list[Import] = []
	named_imports: list[Import] = []
	type_imports: list[Import] = []
	has_side_effect = False

	for imp in imports:
		if imp.is_side_effect:
			has_side_effect = True
		elif imp.is_namespace:
			namespace_imports.append(imp)
		elif imp.is_default:
			if imp.is_type_only:
				type_imports.append(imp)
			else:
				default_imports.append(imp)
		else:
			if imp.is_type_only:
				type_imports.append(imp)
			else:
				named_imports.append(imp)

	lines: list[str] = []

	# Namespace import (only one allowed per source)
	if namespace_imports:
		imp = namespace_imports[0]
		lines.append(f'import * as {imp.js_name} from "{src}";')

	# Default import (only one allowed per source)
	if default_imports:
		imp = default_imports[0]
		lines.append(f'import {imp.js_name} from "{src}";')

	# Named imports
	if named_imports:
		members = [f"{imp.name} as {imp.js_name}" for imp in named_imports]
		lines.append(f'import {{ {", ".join(members)} }} from "{src}";')

	# Type imports
	if type_imports:
		type_members: list[str] = []
		for imp in type_imports:
			if imp.is_default:
				type_members.append(f"default as {imp.js_name}")
			else:
				type_members.append(f"{imp.name} as {imp.js_name}")
		lines.append(f'import type {{ {", ".join(type_members)} }} from "{src}";')

	# Side-effect only import (only if no other imports)
	if (
		has_side_effect
		and not default_imports
		and not namespace_imports
		and not named_imports
		and not type_imports
	):
		lines.append(f'import "{src}";')

	return "\n".join(lines)


def _generate_imports_section(imports: Sequence[Import]) -> str:
	"""Generate the full imports section with deduplication and topological ordering."""
	if not imports:
		return ""

	# Deduplicate imports by ID
	seen_ids: set[str] = set()
	unique_imports: list[Import] = []
	for imp in imports:
		if imp.id not in seen_ids:
			seen_ids.add(imp.id)
			unique_imports.append(imp)

	# Group by source
	grouped: dict[str, list[Import]] = {}
	for imp in unique_imports:
		if imp.src not in grouped:
			grouped[imp.src] = []
		grouped[imp.src].append(imp)

	# Topological sort using Import.before constraints (Kahn's algorithm)
	keys = list(grouped.keys())
	if not keys:
		return ""

	index = {k: i for i, k in enumerate(keys)}  # for stability
	indegree: dict[str, int] = {k: 0 for k in keys}
	adj: dict[str, list[str]] = {k: [] for k in keys}

	for src, src_imports in grouped.items():
		for imp in src_imports:
			for before_src in imp.before:
				if before_src in adj:
					adj[src].append(before_src)
					indegree[before_src] += 1

	queue = [k for k, d in indegree.items() if d == 0]
	queue.sort(key=lambda k: index[k])
	ordered: list[str] = []

	while queue:
		u = queue.pop(0)
		ordered.append(u)
		for v in adj[u]:
			indegree[v] -= 1
			if indegree[v] == 0:
				queue.append(v)
				queue.sort(key=lambda k: index[k])

	# Fall back to insertion order if cycle detected
	if len(ordered) != len(keys):
		ordered = keys

	lines: list[str] = []
	for src in ordered:
		stmt = _generate_import_statement(src, grouped[src])
		if stmt:
			lines.append(stmt)

	return "\n".join(lines)


def _collect_function_graph(
	functions: Sequence[AnyJsFunction],
) -> tuple[list[JsConstant], list[AnyJsFunction]]:
	"""Collect all constants and functions in dependency order (depth-first)."""
	seen_funcs: set[str] = set()
	seen_consts: set[str] = set()
	all_funcs: list[AnyJsFunction] = []
	all_consts: list[JsConstant] = []

	def walk(fn: AnyJsFunction) -> None:
		if fn.id in seen_funcs:
			return
		seen_funcs.add(fn.id)

		for dep in fn.deps.values():
			if isinstance(dep, JsFunction):
				walk(dep)
			elif isinstance(dep, JsConstant):
				if dep.id not in seen_consts:
					seen_consts.add(dep.id)
					all_consts.append(dep)

		all_funcs.append(fn)

	for fn in functions:
		walk(fn)

	return all_consts, all_funcs


def _generate_constants_section(constants: Sequence[JsConstant]) -> str:
	"""Generate the constants section."""
	if not constants:
		return ""

	lines: list[str] = ["// Constants"]
	for const in constants:
		js_value = const.expr.emit()
		lines.append(f"const {const.js_name} = {js_value};")

	return "\n".join(lines)


def _generate_functions_section(functions: Sequence[AnyJsFunction]) -> str:
	"""Generate the functions section with actual transpiled code."""
	if not functions:
		return ""

	lines: list[str] = ["// Functions"]
	for fn in functions:
		# fn.transpile() returns "function name_id(args){...}"
		js_code = fn.transpile()
		lines.append(js_code)

	return "\n".join(lines)


def _generate_registry_section(
	all_imports: Sequence[Import],
	lazy_components: Sequence[tuple[ReactComponent[...], Import]] | None = None,
	prop_components: Sequence[ReactComponent[...]] | None = None,
	functions: Sequence[AnyJsFunction] | None = None,
) -> str:
	"""Generate the unified registry containing all imports for runtime lookup."""
	lines: list[str] = []

	# Unified Registry - contains all imports that need to be looked up at runtime
	lines.append("// Unified Registry")
	lines.append("const __registry = {")

	# Add non-type, non-side-effect imports to the registry
	seen_js_names: set[str] = set()
	for imp in all_imports:
		if imp.is_side_effect or imp.is_type_only:
			continue
		if imp.js_name in seen_js_names:
			continue
		seen_js_names.add(imp.js_name)
		lines.append(f'  "{imp.js_name}": {imp.js_name},')

	# Add components with prop access (e.g., AppShell.Header)
	# These need separate registry entries because the lookup key includes the prop
	for comp in prop_components or []:
		if comp.prop:
			# Key is "ImportName_123.PropName", value is ImportName_123.PropName
			key = f"{comp.import_.js_name}.{comp.prop}"
			lines.append(f'  "{key}": {key},')

	# Add lazy components with RenderLazy wrapper
	for comp, render_lazy_imp in lazy_components or []:
		attr = "default" if comp.is_default else comp.name
		prop_accessor = f".{comp.prop}" if comp.prop else ""
		dynamic = f"({{ default: m.{attr}{prop_accessor} }})"
		# Key includes prop if present (e.g., "AppShell_123.Header")
		key = comp.import_.js_name
		if comp.prop:
			key = f"{key}.{comp.prop}"
		lines.append(
			f'  "{key}": {render_lazy_imp.js_name}(() => import("{comp.src}").then((m) => {dynamic})),'
		)

	# Add transpiled functions to the registry
	for fn in functions or []:
		lines.append(f'  "{fn.js_name}": {fn.js_name},')

	lines.append("};")

	return "\n".join(lines)


def generate_route(
	path: str,
	imports: Sequence[Import] | None = None,
	functions: Sequence[AnyJsFunction] | None = None,
	components: Sequence[ReactComponent[...]] | None = None,
	route_file_path: Path | None = None,
	css_dir: Path | None = None,
) -> str:
	"""Generate a route file with all imports, functions, and components.

	Args:
		path: The route path (e.g., "/users/:id")
		imports: Additional imports to include
		functions: JS functions to include
		components: React components used in the route
		route_file_path: Path where the route file will be written (for computing relative imports)
		css_dir: Path to the CSS output directory (for computing relative CSS imports)
	"""
	# 1. Collect lazy component import IDs to exclude from registered_imports
	lazy_import_ids: set[str] = set()
	for comp in components or []:
		if comp.lazy:
			lazy_import_ids.add(comp.import_.id)

	# 2. Collect all imports
	# Start with all registered imports (includes CSS imports from CssImport)
	# but exclude lazy component imports (they're loaded dynamically)
	all_imports: list[Import] = [
		imp for imp in registered_imports() if imp.id not in lazy_import_ids
	]

	# Update src for local CSS imports to use relative paths from the route file
	if route_file_path is not None and css_dir is not None:
		from pulse.javascript_v2.imports import CssImport

		route_dir = route_file_path.parent
		for imp in all_imports:
			if isinstance(imp, CssImport) and imp.is_local:
				# Compute relative path from route file to CSS file
				generated_filename = imp.generated_filename
				assert generated_filename is not None
				css_file_path = css_dir / generated_filename
				rel_path = Path(os.path.relpath(css_file_path, route_dir))
				imp.src = rel_path.as_posix()

	# Add any explicitly passed imports
	if imports:
		all_imports.extend(imports)

	# Add core Pulse imports - store references to use their js_name later
	pulse_view_import = Import.named("PulseView", "pulse-ui-client")

	all_imports.append(pulse_view_import)

	# Check if we need RenderLazy and collect lazy components
	render_lazy_import: Import | None = None
	lazy_components: list[tuple[ReactComponent[...], Import]] = []
	if any(c.lazy for c in (components or [])):
		render_lazy_import = Import.named("RenderLazy", "pulse-ui-client")
		all_imports.append(render_lazy_import)

	# Add component imports and collect components with prop access
	prop_components: list[ReactComponent[...]] = []
	for comp in components or []:
		if comp.lazy:
			if render_lazy_import is not None:
				lazy_components.append((comp, render_lazy_import))
		else:
			all_imports.append(comp.import_)
			# Track components with prop access for registry
			if comp.prop:
				prop_components.append(comp)
		all_imports.extend(comp.extra_imports)

	# 2. Collect function graph (constants + functions in order)
	constants, funcs = _collect_function_graph(list(functions or []))

	# Add imports from functions
	for fn in funcs:
		for imp in fn.imports().values():
			all_imports.append(imp)

	# 3. Generate output sections
	output_parts: list[str] = []

	imports_section = _generate_imports_section(all_imports)
	if imports_section:
		output_parts.append(imports_section)

	output_parts.append("")

	if constants:
		output_parts.append(_generate_constants_section(constants))
		output_parts.append("")

	if funcs:
		output_parts.append(_generate_functions_section(funcs))
		output_parts.append("")

	output_parts.append(
		_generate_registry_section(all_imports, lazy_components, prop_components, funcs)
	)
	output_parts.append("")

	# Route component - use js_name for PulseView
	pulse_view_js = pulse_view_import.js_name
	output_parts.append(f'''const path = "{path}";

export default function RouteComponent() {{
  return (
    <{pulse_view_js} key={{path}} registry={{__registry}} path={{path}} />
  );
}}''')
	output_parts.append("")

	# Headers function
	output_parts.append("""// Action and loader headers are not returned automatically
function hasAnyHeaders(headers) {
  return [...headers].length > 0;
}

export function headers({ actionHeaders, loaderHeaders }) {
  return hasAnyHeaders(actionHeaders) ? actionHeaders : loaderHeaders;
}""")

	return "\n".join(output_parts)
