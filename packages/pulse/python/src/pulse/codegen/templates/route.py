"""Route code generation using transpiler."""

from __future__ import annotations

from collections.abc import Sequence

from pulse.transpiler import (
	Constant,
	Import,
	collect_function_graph,
	emit,
	get_registered_imports,
	registered_constants,
	registered_functions,
)
from pulse.transpiler.emit_context import EmitContext
from pulse.transpiler.function import AnyJsFunction


def _get_import_src(imp: Import) -> str:
	"""Get the import source path, remapping to asset path for local imports."""
	if imp.asset:
		return imp.asset.import_path()
	return imp.src


def _generate_import_statement(
	src: str,
	imports: list[Import],
) -> str:
	"""Generate import statement(s) for a source module.

	Args:
		src: The original source path (may be remapped for local imports)
		imports: List of Import objects for this source
	"""
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
			if imp.is_type:
				type_imports.append(imp)
			else:
				default_imports.append(imp)
		else:
			if imp.is_type:
				type_imports.append(imp)
			else:
				named_imports.append(imp)

	# Remap source path if this is a local import
	import_src = src
	for imp in imports:
		if imp.asset:
			import_src = imp.asset.import_path()
			break

	lines: list[str] = []

	# Namespace import (only one allowed per source)
	if namespace_imports:
		imp = namespace_imports[0]
		lines.append(f'import * as {imp.js_name} from "{import_src}";')

	# Default import (only one allowed per source)
	if default_imports:
		imp = default_imports[0]
		lines.append(f'import {imp.js_name} from "{import_src}";')

	# Named imports
	if named_imports:
		members = [f"{imp.name} as {imp.js_name}" for imp in named_imports]
		lines.append(f'import {{ {", ".join(members)} }} from "{import_src}";')

	# Type imports
	if type_imports:
		type_members: list[str] = []
		for imp in type_imports:
			if imp.is_default:
				type_members.append(f"default as {imp.js_name}")
			else:
				type_members.append(f"{imp.name} as {imp.js_name}")
		lines.append(
			f'import type {{ {", ".join(type_members)} }} from "{import_src}";'
		)

	# Side-effect only import (only if no other imports)
	if (
		has_side_effect
		and not default_imports
		and not namespace_imports
		and not named_imports
		and not type_imports
	):
		lines.append(f'import "{import_src}";')

	return "\n".join(lines)


def _generate_imports_section(imports: Sequence[Import]) -> str:
	"""Generate the full imports section with deduplication and topological ordering.

	Args:
		imports: List of Import objects to generate (should be eager imports only)
	"""
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


def _generate_lazy_imports_section(imports: Sequence[Import]) -> str:
	"""Generate lazy import factories for code-splitting.

	Lazy imports are emitted as factory functions compatible with React.lazy.
	React.lazy requires factories that return { default: Component }.

	For default imports: () => import("./Chart")
	For named imports: () => import("./Chart").then(m => ({ default: m.LineChart }))

	Args:
		imports: List of lazy Import objects
	"""
	if not imports:
		return ""

	lines: list[str] = ["// Lazy imports"]
	for imp in imports:
		import_src = _get_import_src(imp)

		if imp.is_default or imp.is_namespace:
			# Default/namespace: () => import("module") - already has { default }
			factory = f'() => import("{import_src}")'
		else:
			# Named: wrap in { default } for React.lazy compatibility
			factory = (
				f'() => import("{import_src}").then(m => ({{ default: m.{imp.name} }}))'
			)

		lines.append(f"const {imp.js_name} = {factory};")

	return "\n".join(lines)


def _generate_constants_section(constants: Sequence[Constant]) -> str:
	"""Generate the constants section."""
	if not constants:
		return ""

	lines: list[str] = ["// Constants"]
	for const in constants:
		js_value = emit(const.expr)
		lines.append(f"const {const.js_name} = {js_value};")

	return "\n".join(lines)


def _generate_functions_section(functions: Sequence[AnyJsFunction]) -> str:
	"""Generate the functions section with actual transpiled code."""
	if not functions:
		return ""

	lines: list[str] = ["// Functions"]
	for fn in functions:
		js_code = emit(fn.transpile())
		lines.append(js_code)

	return "\n".join(lines)


def _generate_registry_section(
	imports: Sequence[Import],
	constants: Sequence[Constant],
	functions: Sequence[AnyJsFunction],
) -> str:
	"""Generate the unified registry from all registered entities.

	The registry contains all values that need to be looked up at runtime,
	keyed by their unique ID.
	"""
	lines: list[str] = []
	lines.append("// Unified Registry")
	lines.append("const __registry = {")

	# Add imports
	for imp in imports:
		if not imp.is_side_effect:
			lines.append(f'  "{imp.id}": {imp.js_name},')

	# Add constants
	for const in constants:
		lines.append(f'  "{const.id}": {const.js_name},')

	# Add functions
	for fn in functions:
		lines.append(f'  "{fn.id}": {fn.js_name},')

	lines.append("};")

	return "\n".join(lines)


def generate_route(
	path: str,
	route_file_path: str,
) -> str:
	"""Generate a route file with all registered imports, functions, and components.

	Args:
		path: The route path (e.g., "/users/:id")
		route_file_path: Path from pulse root (e.g., "routes/users/index.tsx")
	"""
	with EmitContext(route_file_path=route_file_path):
		# Add core Pulse imports
		pulse_view_import = Import("PulseView", "pulse-ui-client")

		# Collect function graph (constants + functions in dependency order)
		fn_constants, funcs = collect_function_graph(registered_functions())

		# Include all registered constants (not just function dependencies)
		# This ensures constants used as component tags are included
		fn_const_ids = {c.id for c in fn_constants}
		all_constants = list(fn_constants)
		for const in registered_constants():
			if const.id not in fn_const_ids:
				all_constants.append(const)
		constants = all_constants

		# Get all registered imports and split by lazy flag
		all_imports = list(get_registered_imports())
		eager_imports = [imp for imp in all_imports if not imp.lazy]
		lazy_imports = [imp for imp in all_imports if imp.lazy]

		# Generate output sections
		output_parts: list[str] = []

		# Eager imports (ES6 import statements)
		imports_section = _generate_imports_section(eager_imports)
		if imports_section:
			output_parts.append(imports_section)

		output_parts.append("")

		# Lazy imports (factory functions)
		lazy_section = _generate_lazy_imports_section(lazy_imports)
		if lazy_section:
			output_parts.append(lazy_section)
			output_parts.append("")

		if constants:
			output_parts.append(_generate_constants_section(constants))
			output_parts.append("")

		if funcs:
			output_parts.append(_generate_functions_section(funcs))
			output_parts.append("")

		# Generate the unified registry including all imports, constants and functions
		output_parts.append(_generate_registry_section(all_imports, constants, funcs))
		output_parts.append("")

		# Route component
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
