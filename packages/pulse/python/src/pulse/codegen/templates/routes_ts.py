from mako.template import Template

# Mako template for routes configuration
# Uses Pulse router with dynamic imports for automatic code splitting
ROUTES_CONFIG_TEMPLATE = Template(
	"""export interface RouteNode {
  path: string;
  component?: () => Promise<{ default: React.ComponentType<any> }>;
  children?: RouteNode[];
}

export const routes: RouteNode[] = [
${routes_str}
];
"""
)

# Runtime route tree for matching (used by main layout loader)
ROUTES_RUNTIME_TEMPLATE = Template(
	"""import type { RouteObject } from "react-router";

export type RRRouteObject = RouteObject & {
  id: string;
  uniquePath?: string;
  children?: RRRouteObject[];
  file: string;
}

export const rrPulseRouteTree = ${routes_str} satisfies RRRouteObject[];
"""
)
