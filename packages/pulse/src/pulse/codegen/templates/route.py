from typing import Iterable, Sequence, TypedDict
from mako.template import Template
from pulse.codegen.js import ExternalJsFunction, JsFunction
from pulse.codegen.utils import NameRegistry
from ..imports import ImportStatement, Imports
from pulse.react_component import ReactComponent


class ComponentInfo(TypedDict):
    key: str
    expr: str
    src: str
    name: str
    default: bool
    lazy: bool
    dynamic: str


class RouteTemplate:
    """
    Helper to resolve names and build import statements before rendering a route file.

    - Maintains a per-file NameRegistry seeded with RESERVED_NAMES (plus user-provided)
    - Uses Imports to avoid collisions across default/named/type imports
    - Computes SSR expressions and lazy dynamic selectors for React components
    - Reserves identifiers for local JS functions
    """

    def __init__(
        self, reserved_names: Iterable[str] | None = None
    ) -> None:
        initial = set(reserved_names or []).union(RESERVED_NAMES)
        self.names = NameRegistry(initial)
        self._imports = Imports([], names=self.names)
        self.components_by_key: dict[str, ComponentInfo] = {}
        self._js_local_names: dict[str, str] = {}
        self.needs_render_lazy: bool = False

    def add_components(self, components: Sequence[ReactComponent]) -> None:
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

    def add_external_js(self, fns: Sequence[ExternalJsFunction]) -> None:
        for fn in fns:
            self._imports.import_(fn.src, fn.name, is_default=True)
        # TODO: update fn in case of aliasing

    def reserve_js_function_names(self, js_functions: Sequence[JsFunction]) -> None:
        for j in js_functions:
            self._js_local_names[j.name] = self.names.register(j.name)
        # TODO: update fn in case of aliasing

    def context(self) -> dict[str, object]:
        # Deterministic order of import sources with ordering constraints
        import_sources = self._imports.ordered_sources()
        return {
            "import_sources": import_sources,
            "components_ctx": list(self.components_by_key.values()),
            "local_js_names": self._js_local_names,
            "needs_render_lazy": self.needs_render_lazy,
        }


def dynamic_selector(comp: ReactComponent):
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
    "VDOM",
    "ComponentRegistry",
    "RenderLazy",
]

TEMPLATE = Template(
    """import { type HeadersArgs } from "react-router";
import { PulseView, type VDOM, type ComponentRegistry${", " + "RenderLazy" if needs_render_lazy else ""} } from "pulse-ui-client";

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
    <PulseView key={path} externalComponents={externalComponents} path={path} />
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
    route,
    components: Sequence[ReactComponent] | None = None,
    js_functions: Sequence[JsFunction] | None = None,
    external_js: Sequence[ExternalJsFunction] | None = None,
    reserved_names: Iterable[str] | None = None,
) -> str:
    comps = list(components or [])

    jt = RouteTemplate(reserved_names=reserved_names)
    jt.add_components(comps)
    if external_js:
        jt.add_external_js(list(external_js))
    if js_functions:
        jt.reserve_js_function_names(list(js_functions))

    ctx = jt.context() | {"route": route}
    return str(TEMPLATE.render_unicode(**ctx))
