from mako.template import Template

# Mako template for the main layout
LAYOUT_TEMPLATE = Template(
    """import { PulseProvider, type PulseConfig } from "${lib_path}/pulse";
import { Outlet } from "react-router";

// This config is imported by the layout and used to initialize the client
export const config: PulseConfig = {
  serverAddress: "${server_address}",
};

export default function PulseLayout() {
  return (
    <PulseProvider config={config}>
      <Outlet />
    </PulseProvider>
  );
}
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

# Mako template for server-rendered pages
ROUTE_TEMPLATE = Template(
    """import { redirect, type LoaderFunctionArgs } from "react-router";
import { PulseView } from "${lib_path}/pulse";
import type { VDOM, ComponentRegistry } from "${lib_path}/vdom";
import { extractServerRouteInfo } from "${lib_path}/messages";

% if components:
// Component imports
% for component in components:
% if component.is_default:
import ${component.tag} from "${component.import_path}";
% else:
% if component.alias:
import { ${component.tag} as ${component.alias} } from "${component.import_path}";
% else:
import { ${component.tag} } from "${component.import_path}";
% endif
% endif
% endfor

// Component registry
const externalComponents: ComponentRegistry = {
% for component in components:
  "${component.key}": ${component.alias or component.tag},
% endfor
};
% else:
// No components needed for this route
const externalComponents: ComponentRegistry = {};
% endif

const path = "${route.unique_path()}";

export async function loader(args: LoaderFunctionArgs) {
  const routeInfo = extractServerRouteInfo(args);
  // Forward inbound headers (cookies, auth, user-agent, etc.) to the Python server
  const fwd = new Headers(args.request.headers);
  // These request-specific headers must be recomputed for the new request
  fwd.delete("content-length");
  // Ensure JSON body content type
  fwd.set("content-type", "application/json");
  const res = await fetch("${server_address}" + "/prerender/" + path, {
    method: "POST",
    headers: fwd,
    body: JSON.stringify(routeInfo),
    redirect: "manual",
  });
  if (res.status === 404) {
    return redirect("/not-found");
  }
  if (res.status === 302 || res.status === 301) {
    const location = res.headers.get("Location");
    if (location) {
      return redirect(location);
    }
  }
  if (!res.ok) {
    throw new Error(
      "Failed to fetch prerender route /"+ path+ ": " + res.status + " " + res.statusText
    );
  }
  const vdom = await res.json();
  return vdom;
}

export default function RouteComponent({ loaderData }: { loaderData: VDOM }) {
  return (
    <PulseView
      key={path}
      initialVDOM={loaderData}
      externalComponents={externalComponents}
      path={path}
    />
  );
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
