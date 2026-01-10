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
	"""// Pulse route node type (custom router, no react-router dependency)
export interface PulseRouteNode {
  id: string;
  path?: string;
  uniquePath?: string;
  children?: PulseRouteNode[];
  file: string;
}

export const pulseRouteTree = ${routes_str} satisfies PulseRouteNode[];
"""
)
