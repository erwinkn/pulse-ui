from collections.abc import Iterable, Sequence
from typing import TypedDict, TypeVarTuple

from mako.template import Template

from pulse.codegen.imports import Import, Imports, ImportStatement
from pulse.codegen.utils import NameRegistry
from pulse.javascript_v2.function import JsFunction
from pulse.react_component import ReactComponent
from pulse.routing import Layout, Route

Args = TypeVarTuple("Args")


class ComponentInfo(TypedDict):
	key: str
	expr: str
	src: str
	name: str
	default: bool
	lazy: bool
	dynamic: str


class CssModuleImport(TypedDict):
	id: str
	import_path: str


class CssModuleCtx(TypedDict):
	id: str
	identifier: str


class RouteTemplate:
	"""
	Helper to resolve names and build import statements before rendering a route file.

	- Maintains a per-file NameRegistry seeded with RESERVED_NAMES (plus user-provided)
	- Uses Imports to avoid collisions across default/named/type imports
	- Computes SSR expressions and lazy dynamic selectors for React components
	- Reserves identifiers for local JS functions
	"""

	names: NameRegistry
	_imports: Imports

	def __init__(self, reserved_names: Iterable[str] | None = None) -> None:
		initial = set(reserved_names or []).union(RESERVED_NAMES)
		self.names = NameRegistry(initial)
		self._imports = Imports(names=self.names)
		self.components_by_key: dict[str, ComponentInfo] = {}
		self._js_local_names: dict[str, str] = {}
		self.needs_render_lazy: bool = False
		self._css_modules: dict[str, CssModuleCtx] = {}

	def add_components(self, components: "Sequence[ReactComponent[...]]") -> None:
		for comp in components:
			if comp.lazy:
				self.needs_render_lazy = True
				# We still register the name as it's an easy way to guarantee a unique component key
				ident = self.names.register(comp.name)
				if ident != comp.name:
					comp.alias = ident
			else:
				# For SSR-capable components, import the symbol and compute expression
				ident = self._imports.import_(
					comp.src, comp.name, is_default=comp.is_default
				)
				if ident != comp.name:
					comp.alias = ident

			key = comp.expr
			existing = self.components_by_key.get(key)
			if existing:
				same_import = (
					existing["src"] == comp.src
					and existing["name"] == comp.name
					and existing["default"] == comp.is_default
				)
				if not same_import:
					raise RuntimeError(
						"Invariant violation: two React components ended up with the same key. This is a Pulse bug, please raise an issue: https://github.com/erwinkn/pulse-ui"
					)

			self.components_by_key[key] = {
				"key": key,
				"lazy": comp.lazy,
				"expr": comp.expr,
				"src": comp.src,
				"name": comp.name,
				"default": comp.is_default,
				"dynamic": dynamic_selector(comp),
			}

			# Register component-level extra imports (e.g., side-effect CSS)
			extra_imports = getattr(comp, "extra_imports", None) or []
			for stmt in extra_imports:
				if isinstance(stmt, ImportStatement):
					self._imports.add_statement(stmt)

	def add_css_modules(self, modules: Sequence[CssModuleImport]) -> None:
		for mod in modules:
			if mod["id"] in self._css_modules:
				continue
			identifier = self._imports.import_(
				mod["import_path"], mod["id"], is_default=True
			)
			self._css_modules[mod["id"]] = {
				"id": mod["id"],
				"identifier": identifier,
			}

	def add_css_imports(self, imports: Sequence[str]) -> None:
		for spec in imports:
			self._imports.add(Import.css(spec, register=False))

	def add_js_imports(self, imports: Sequence[Import]) -> None:
		"""Add JS imports to the route."""
		for imp in imports:
			self._imports.add(imp)

	def reserve_js_function_names(
		self, js_functions: "Sequence[JsFunction[*Args, object]]"
	) -> None:
		for j in js_functions:
			fn_name = j.fn.__name__
			self._js_local_names[fn_name] = self.names.register(fn_name)

	def context(self) -> dict[str, object]:
		# Deterministic order of import sources with ordering constraints
		import_sources = self._imports.ordered_sources()
		return {
			"import_sources": import_sources,
			"components_ctx": list(self.components_by_key.values()),
			"local_js_names": self._js_local_names,
			"needs_render_lazy": self.needs_render_lazy,
			"css_modules_ctx": list(self._css_modules.values()),
		}


def dynamic_selector(comp: "ReactComponent[...]"):
	# Dynamic import mapping for lazy usage on the client
	attr = "default" if comp.is_default else comp.name
	prop_accessor = f".{comp.prop}" if comp.prop else ""
	return f"({{ default: m.{attr}{prop_accessor} }})"


# Constants and functions defined in the template below. We need to avoid name conflicts with imports
RESERVED_NAMES = [
	"externalComponents",
	"path",
	"RouteComponent",
	"hasAnyHeaders",
	"headers",
	"HeadersArgs",
	"PulseView",
	"ComponentRegistry",
	"RenderLazy",
	"cssModules",
]

TEMPLATE = Template(
	"""import { PulseView, type ComponentRegistry${", " + "RenderLazy" if needs_render_lazy else ""} } from "pulse-ui-client";
import type { HeadersArgs } from "react-router";

% if import_sources:
// Component and helper imports
% for import_source in import_sources:
%   if import_source.default_import:
import ${import_source.default_import} from "${import_source.src}";
%   endif
%   if import_source.values:
import { ${', '.join([f"{v.name}{f' as {v.alias}' if v.alias else ''}" for v in import_source.values])} } from "${import_source.src}";
%   endif
%   if import_source.types:
import type { ${', '.join([f"{t.name}{f' as {t.alias}' if t.alias else ''}" for t in import_source.types])} } from "${import_source.src}";
%   endif
%   if import_source.side_effect and (not import_source.default_import) and (not import_source.values) and (not import_source.types):
import "${import_source.src}";
%   endif
% endfor
% endif

// Component registry
% if css_modules_ctx:
const cssModules = {
% for mod in css_modules_ctx:
  "${mod['id']}": ${mod['identifier']},
% endfor
};
% else:
const cssModules = {};
% endif

% if components_ctx:
const externalComponents: ComponentRegistry = {
% for c in components_ctx:
%   if c['lazy']:
  "${c['key']}": RenderLazy(() => import("${c['src']}").then((m) => ${c['dynamic']})),
%   else:
  "${c['key']}": ${c['expr']},
%   endif
% endfor
};
% else:
// No components needed for this route
const externalComponents: ComponentRegistry = {};
% endif

const path = "${route.unique_path()}";

export default function RouteComponent() {
  return (
    <PulseView key={path} externalComponents={externalComponents} path={path} cssModules={cssModules} />
  );
}

// Action and loader headers are not returned automatically
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
}
"""
)

# Back-compat alias
ROUTE_TEMPLATE = TEMPLATE


def render_route(
	*,
	route: Route | Layout,
	components: Sequence[ReactComponent[...]] | None = None,
	css_modules: Sequence[CssModuleImport] | None = None,
	css_imports: Sequence[str] | None = None,
	js_functions: "Sequence[JsFunction[*Args, object]] | None" = None,
	js_imports: Sequence[Import] | None = None,
	reserved_names: Iterable[str] | None = None,
) -> str:
	comps = list(components or [])

	jt = RouteTemplate(reserved_names=reserved_names)
	jt.add_components(comps)
	modules = list(css_modules or [])
	if modules:
		jt.add_css_modules(modules)
	imports = list(css_imports or [])
	if imports:
		jt.add_css_imports(imports)
	if js_imports:
		jt.add_js_imports(list(js_imports))
	if js_functions:
		jt.reserve_js_function_names(list(js_functions))

	ctx = jt.context() | {"route": route}
	return str(TEMPLATE.render_unicode(**ctx))
