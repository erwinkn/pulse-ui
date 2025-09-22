import { route, type RouteConfig } from "@react-router/dev/routes";
import { routes as pulseRoutes } from "./pulse/routes";

export default [
  ...pulseRoutes,
  route("/app-shell", "appshell.tsx"),
] satisfies RouteConfig;
