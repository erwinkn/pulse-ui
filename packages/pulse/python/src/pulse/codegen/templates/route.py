"""Route code generation using the javascript_v2 import system."""

from __future__ import annotations

from collections.abc import Sequence

from pulse.css import CssImport, CssModule
from pulse.javascript_v2.constants import JsConstant
from pulse.javascript_v2.function import AnyJsFunction, JsFunction
from pulse.javascript_v2.imports import Import
from pulse.react_component import ReactComponent


def _generate_import_statement(src: str, imports: list[Import]) -> str:
	"""Generate import statement(s) for a source module."""
	default_imports: list[Import] = []
	named_imports: list[Import] = []
	type_imports: list[Import] = []
	has_side_effect = False

	for imp in imports:
		if imp.is_side_effect:
			has_side_effect = True
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
	"""Generate the functions section (placeholder stubs for now)."""
	if not functions:
		return ""

	lines: list[str] = ["// Functions"]
	for fn in functions:
		# TODO: Actual transpilation will be implemented later
		lines.append(f"function {fn.js_name}() {{")
		lines.append("  // TODO: transpiled body")
		lines.append("}")

	return "\n".join(lines)


def _generate_registries_section(
	css_modules: Sequence[tuple[CssModule, Import]],
	functions: Sequence[AnyJsFunction],
	components: Sequence[ReactComponent[...]],
) -> str:
	"""Generate the registries section (cssModules, functions, externalComponents)."""
	lines: list[str] = []

	# CSS Modules Registry
	lines.append("// CSS Modules Registry")
	if css_modules:
		lines.append("const cssModules = {")
		for module, imp in css_modules:
			lines.append(f'  "{module.id}": {imp.js_name},')
		lines.append("};")
	else:
		lines.append("const cssModules = {};")

	lines.append("")

	# Functions Registry
	lines.append("// Functions Registry")
	if functions:
		lines.append("const functions = {")
		for fn in functions:
			lines.append(f'  "{fn.fn.__name__}": {fn.js_name},')
		lines.append("};")
	else:
		lines.append("const functions = {};")

	lines.append("")

	# Components Registry
	lines.append("// Components Registry")
	if components:
		lines.append("const externalComponents: ComponentRegistry = {")
		for comp in components:
			if comp.lazy:
				attr = "default" if comp.is_default else comp.name
				prop_accessor = f".{comp.prop}" if comp.prop else ""
				dynamic = f"({{ default: m.{attr}{prop_accessor} }})"
				lines.append(
					f'  "{comp.expr}": RenderLazy(() => import("{comp.src}").then((m) => {dynamic})),'
				)
			else:
				js_expr = comp.import_.js_name
				if comp.prop:
					js_expr = f"{js_expr}.{comp.prop}"
				lines.append(f'  "{comp.expr}": {js_expr},')
		lines.append("};")
	else:
		lines.append("const externalComponents: ComponentRegistry = {};")

	return "\n".join(lines)


def generate_route(
	path: str,
	imports: Sequence[Import] | None = None,
	css_modules: Sequence[tuple[CssModule, str]] | None = None,
	css_imports: Sequence[tuple[CssImport, str]] | None = None,
	functions: Sequence[AnyJsFunction] | None = None,
	components: Sequence[ReactComponent[...]] | None = None,
) -> str:
	"""Generate a route file with all imports, functions, and components."""
	# 1. Collect all imports
	all_imports: list[Import] = list(imports or [])
	css_module_imports: list[tuple[CssModule, Import]] = []

	# Add core Pulse imports
	all_imports.extend(
		[
			Import.named("PulseView", "pulse-ui-client"),
			Import.type_("ComponentRegistry", "pulse-ui-client"),
			Import.type_("HeadersArgs", "react-router"),
		]
	)

	# Check if we need RenderLazy
	if any(c.lazy for c in (components or [])):
		all_imports.append(Import.named("RenderLazy", "pulse-ui-client"))

	# Add CSS module imports (convert CssModule to default Import)
	for module, import_path in css_modules or []:
		imp = Import.default(module.id, import_path)
		all_imports.append(imp)
		css_module_imports.append((module, imp))

	# Add CSS side-effect imports
	for _, import_path in css_imports or []:
		all_imports.append(Import.side_effect(import_path))

	# Add component imports
	for comp in components or []:
		if not comp.lazy:
			all_imports.append(comp.import_)
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
		_generate_registries_section(css_module_imports, funcs, list(components or []))
	)
	output_parts.append("")

	# Route component
	output_parts.append(f'''const path = "{path}";

export default function RouteComponent() {{
  return (
    <PulseView key={{path}} externalComponents={{externalComponents}} path={{path}} cssModules={{cssModules}} functions={{functions}} />
  );
}}''')
	output_parts.append("")

	# Headers function
	output_parts.append("""// Action and loader headers are not returned automatically
function hasAnyHeaders(headers: Headers): boolean {
  return [...headers].length > 0;
}

export function headers({
  actionHeaders,
  loaderHeaders,
}: HeadersArgs) {
  return hasAnyHeaders(actionHeaders)
    ? actionHeaders
    : loaderHeaders;
}""")

	return "\n".join(output_parts)
