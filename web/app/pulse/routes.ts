import {
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
  layout("pulse/_layout.tsx", rrPulseRouteTree.map(toDevRoute)),
] satisfies RouteConfig;
