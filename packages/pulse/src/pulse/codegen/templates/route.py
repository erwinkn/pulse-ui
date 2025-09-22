from typing import Iterable, Sequence
from mako.template import Template
from pulse.codegen.js import ExternalJsFunction, JsFunction
from pulse.codegen.utils import NameRegistry
from ..imports import ImportStatement, Imports
from pulse.react_component import ReactComponent


class JsTemplate:
    """
    Helper to resolve names and build import statements before rendering a route file.

    - Maintains a per-file NameRegistry seeded with RESERVED_NAMES (plus user-provided)
    - Uses Imports to avoid collisions across default/named/type imports
    - Computes SSR expressions and lazy dynamic selectors for React components
    - Reserves identifiers for local JS functions
    """

    def __init__(self, reserved_names: Iterable[str] | None = None) -> None:
        initial = set(reserved_names or []).union(RESERVED_NAMES)
        self.names = NameRegistry(initial)
        self._imports = Imports([], names=self.names)
        self._components_by_key: dict[str, dict[str, object]] = {}
        self._js_local_names: dict[str, str] = {}
        self._needs_render_lazy: bool = False
        self._lib_path: str | None = None
        # Core identifiers (allocated now to prevent collisions later)
        self._ident_headers_args = self.names.register("HeadersArgs")
        self._ident_pulse_view = self.names.register("PulseView")
        self._ident_render_lazy = self.names.register("RenderLazy")
        self._ident_vdom = self.names.register("VDOM")
        self._ident_component_registry = self.names.register("ComponentRegistry")

    def add_core_imports(self, *, lib_path: str, needs_render_lazy: bool) -> None:
        # Store core info; actual core imports are rendered explicitly to preserve format
        self._lib_path = lib_path
        self._needs_render_lazy = needs_render_lazy

    def add_components(self, components: Sequence[ReactComponent]) -> None:
        for comp in components:
            # Derive base symbol and property for dotted component names if prop not explicitly given
            base_name = comp.name
            prop_name = comp.prop
            if "." in base_name and prop_name is None:
                base_name, prop_name = base_name.split(".", 1)

            # For SSR-capable components, import the symbol and compute expression
            ssr_expr: str | None = None
            if not getattr(comp, "lazy", False):
                if comp.is_default:
                    ident = self._imports.import_(comp.src, base_name, is_default=True)
                else:
                    ident = self._imports.import_(comp.src, base_name)
                ssr_expr = f"{ident}.{prop_name}" if prop_name else ident

            # Compute the canonical expression string used as the registry key
            expr_key = f"{base_name}.{prop_name}" if prop_name else base_name

            # Dynamic import mapping for lazy usage on the client
            if comp.is_default:
                if prop_name:
                    dyn_selector = f"({{ default: m.default.{prop_name} }})"
                else:
                    dyn_selector = "({ default: m.default })"
            else:
                if prop_name:
                    dyn_selector = f"({{ default: m.{base_name}.{prop_name} }})"
                else:
                    dyn_selector = f"({{ default: m.{base_name} }})"

            # Last write wins for duplicate keys
            self._components_by_key[expr_key] = {
                "key": expr_key,
                "lazy": bool(getattr(comp, "lazy", False)),
                "ssr_expr": ssr_expr,
                "dynamic_src": comp.src,
                "dynamic_selector": dyn_selector,
            }

    def add_external_js(self, fns: Sequence[ExternalJsFunction]) -> None:
        for fn in fns:
            if fn.is_default:
                self._imports.import_(fn.src, fn.name, is_default=True)
            else:
                self._imports.import_(fn.src, fn.name)

    def reserve_js_function_names(self, js_functions: Sequence[JsFunction]) -> None:
        for j in js_functions:
            self._js_local_names[j.name] = self.names.register(j.name)

    @property
    def needs_render_lazy(self) -> bool:
        return self._needs_render_lazy

    @property
    def lib_path(self) -> str:
        if self._lib_path is None:
            # Default to pulse-ui-client if not set explicitly
            return "pulse-ui-client"
        return self._lib_path

    def context(self) -> dict[str, object]:
        # Deterministic order of import sources
        import_sources = list(self._imports.sources.values())
        return {
            "import_sources": import_sources,
            "components_ctx": list(self._components_by_key.values()),
            "local_js_names": self._js_local_names,
            "needs_render_lazy": self._needs_render_lazy,
            "lib_path": self.lib_path,
            "ident_headers_args": self._ident_headers_args,
            "ident_pulse_view": self._ident_pulse_view,
            "ident_render_lazy": self._ident_render_lazy,
            "ident_vdom": self._ident_vdom,
            "ident_component_registry": self._ident_component_registry,
        }


IMPORTS: list[ImportStatement] = []
# Constants and functions defined in the template below. We need to avoid name conflicts with imports
RESERVED_NAMES = [
    "externalComponents",
    "path",
    "RouteComponent",
    "hasAnyHeaders",
    "headers",
]

TEMPLATE = Template(
    """import { type ${ident_headers_args} } from "react-router";
import { ${ident_pulse_view}, type ${ident_vdom}, type ${ident_component_registry}${", " + ident_render_lazy if needs_render_lazy else ""} } from "${lib_path}";

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
% endfor
% endif

// Component registry
% if components_ctx:
const externalComponents: ${ident_component_registry} = {
% for c in components_ctx:
%   if c['lazy']:
  "${c['key']}": RenderLazy(() => import("${c['dynamic_src']}").then((m) => ${c['dynamic_selector']})),
%   else:
  "${c['key']}": ${c['ssr_expr']},
%   endif
% endfor
};
% else:
// No components needed for this route
const externalComponents: ${ident_component_registry} = {};
% endif

const path = "${route.unique_path()}";

export default function RouteComponent() {
  return (
    <${ident_pulse_view} key={path} externalComponents={externalComponents} path={path} />
  );
}

// Action and loader headers are not returned automatically
function hasAnyHeaders(headers: Headers): boolean {
  return [...headers].length > 0;
}

export function headers({
  actionHeaders,
  loaderHeaders,
}: ${ident_headers_args}) {
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
    route,
    lib_path: str,
    components: Sequence[ReactComponent] | None = None,
    js_functions: Sequence[JsFunction] | None = None,
    external_js: Sequence[ExternalJsFunction] | None = None,
    reserved_names: Iterable[str] | None = None,
) -> str:
    comps = list(components or [])
    needs_render_lazy = any(getattr(c, "lazy", False) for c in comps)

    jt = JsTemplate(reserved_names=reserved_names)
    jt.add_core_imports(lib_path=lib_path, needs_render_lazy=needs_render_lazy)
    jt.add_components(comps)
    if external_js:
        jt.add_external_js(list(external_js))
    if js_functions:
        jt.reserve_js_function_names(list(js_functions))

    ctx = jt.context() | {"route": route}
    return str(TEMPLATE.render_unicode(**ctx))
