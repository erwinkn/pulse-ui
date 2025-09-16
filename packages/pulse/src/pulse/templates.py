from mako.template import Template

# Mako template for the main layout
LAYOUT_TEMPLATE = Template(
    """import { extractServerRouteInfo, PulseProvider, type PulseConfig, type PulsePrerender } from "${lib_path}";
import { Outlet, data, type LoaderFunctionArgs, type ClientLoaderFunctionArgs } from "react-router";
import { matchRoutes } from "react-router";
import { rrPulseRouteTree } from "./routes.runtime";
import { useLoaderData } from "react-router";

// This config is imported by the layout and used to initialize the client
export const config: PulseConfig = {
  serverAddress: "${server_address}",
};


// Server loader: perform initial prerender, abort on first redirect/not-found
export async function loader(args: LoaderFunctionArgs) {
  const url = new URL(args.request.url);
  const matches = matchRoutes([rrPulseRouteTree], url.pathname) ?? [];
  const paths = matches.map(m => m.route.uniquePath);
  const fwd = new Headers(args.request.headers);
  fwd.delete("content-length");
  fwd.set("content-type", "application/json");
  const res = await fetch("${server_address}/prerender", {
    method: "POST",
    headers: fwd,
    body: JSON.stringify({ paths, routeInfo: extractServerRouteInfo(args) }),
  });
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  if (body.redirect) return new Response(null, { status: 302, headers: { Location: body.redirect } });
  if (body.notFound) return new Response(null, { status: 404 });
  const prerenderData = body as PulsePrerender;
  const setCookies =
    (res.headers.getSetCookie?.() as string[] | undefined) ??
    (res.headers.get("set-cookie") ? [res.headers.get("set-cookie") as string] : []);
  const headers = new Headers();
  for (const c of setCookies) headers.append("Set-Cookie", c);
  return data(prerenderData, { headers });
}

// Client loader: re-prerender on navigation while reusing renderId
export async function clientLoader(args: ClientLoaderFunctionArgs) {
  const url = new URL(args.request.url);
  const matches = matchRoutes([rrPulseRouteTree], url.pathname) ?? [];
  const paths = matches.map(m => m.route.uniquePath);
  const renderId = 
    typeof window !== "undefined" && typeof sessionStorage !== "undefined"
      ? (sessionStorage.getItem("__PULSE_RENDER_ID") ?? undefined) 
      : undefined;
  const res = await fetch("${server_address}/prerender", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ paths, routeInfo: extractServerRouteInfo(args), renderId }),
  });
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  if (body.redirect) return new Response(null, { status: 302, headers: { Location: body.redirect } });
  if (body.notFound) return new Response(null, { status: 404 });
  return body as PulsePrerender;
}

export default function PulseLayout() {
  const data = useLoaderData<typeof loader>();
  if (typeof window !== "undefined" && typeof sessionStorage !== "undefined") {
    sessionStorage.setItem("__PULSE_RENDER_ID", data.renderId);
  }
  return (
    <PulseProvider config={config} prerender={data}>
      <Outlet />
    </PulseProvider>
  );
}
// Persist renderId in sessionStorage for reuse in clientLoader is handled within the component
"""
)

# Mako template for routes configuration
ROUTES_CONFIG_TEMPLATE = Template(
    """import {
  type RouteConfig,
  route,
  layout,
  index,
} from "@react-router/dev/routes";

export const routes = [
  layout("${pulse_dir}/_layout.tsx", [
${routes_str}
  ]),
] satisfies RouteConfig;
"""
)

# Runtime route tree for matching (used by loader experiments)
ROUTES_RUNTIME_TEMPLATE = Template(
    """import type { RouteObject } from "react-router";

export type RRRouteObject = RouteObject & {
  id: string;
  uniquePath?: string;
  children?: RRRouteObject[];
}

export const rrPulseRouteTree = ${routes_str} satisfies RRRouteObject;
"""
)

# Mako template for server-rendered pages
ROUTE_TEMPLATE = Template(
    """import { type HeadersArgs } from "react-router";
import { PulseView, type VDOM, type ComponentRegistry${", RenderLazy" if components and any(c.lazy for c in components) else ""} } from "${lib_path}";

% if components:
// Component imports
% for component in components:
% if not component.lazy:
% if component.is_default:
import ${component.tag} from "${component.import_path}";
% else:
% if component.alias:
import { ${component.tag} as ${component.alias} } from "${component.import_path}";
% else:
import { ${component.tag} } from "${component.import_path}";
% endif
% endif
% endif
% endfor

// Component registry
const externalComponents: ComponentRegistry = {
% for component in components:
% if component.lazy:
  // Lazy loaded on client
  "${component.key}": RenderLazy(() => import("${component.import_path}").then((m) => ({ default: m.${'default' if component.is_default else (component.alias or component.tag)} }))),
% else:
  // SSR-capable import
  "${component.key}": ${component.alias or component.tag},
% endif
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

# => DEPRECATED
# Mako template for pre-rendered route pages
# PRERENDERED_ROUTE_TEMPLATE = Template(
#     """import { PulseView } from "${lib_path}/pulse";
# import type { VDOM, ComponentRegistry } from "${lib_path}/vdom";

# % if components:
# // Component imports
# % for component in components:
# % if component.is_default:
# import ${component.tag} from "${component.import_path}";
# % else:
# % if component.alias:
# import { ${component.tag} as ${component.alias} } from "${component.import_path}";
# % else:
# import { ${component.tag} } from "${component.import_path}";
# % endif
# % endif
# % endfor

# // Component registry
# const externalComponents: ComponentRegistry = {
# % for component in components:
#   "${component.key}": ${component.alias or component.tag},
# % endfor
# };
# % else:
# // No components needed for this route
# const externalComponents: ComponentRegistry = {};
# % endif

# // The initial VDOM is bootstrapped from the server
# const initialVDOM: VDOM = ${vdom};

# const path = "${route.unique_path()}";

# export default function RouteComponent() {
#   return (
#     <PulseView
#       initialVDOM={initialVDOM}
#       externalComponents={externalComponents}
#       path={path}
#     />
#   );
# }
# """
# )
