from mako.template import Template

# Mako template for routes configuration
ROUTES_CONFIG_TEMPLATE = Template(
    """import {
  type RouteConfig,
  route,
  layout,
  index,
} from "@react-router/dev/routes";
import { rrPulseRouteTree, type RRRouteObject } from "./routes.runtime";

function toDevRoute(node: RRRouteObject): any {
  const children = (node.children ?? []).map(toDevRoute);
  if (node.index) return index(node.file!);
  if (node.path !== undefined) {
    return children.length ? route(node.path, node.file!, children) : route(node.path, node.file!);
  }
  // Layout node (pathless)
  return layout(node.file!, children);
}

export const routes = [
  layout("${pulse_dir}/_layout.tsx", rrPulseRouteTree.map(toDevRoute)),
] satisfies RouteConfig;
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