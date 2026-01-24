from mako.template import Template

ROUTES_MANIFEST_TEMPLATE = Template(
	"""import type { PulseRoute, RouteLoaderMap } from "pulse-ui-client";

export const pulseRouteTree = ${routes_str} satisfies PulseRoute[];

export const routeLoaders = ${loaders_str} satisfies RouteLoaderMap;
"""
)
