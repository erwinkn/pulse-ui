import { route, type RouteConfig } from "@react-router/dev/routes";
import { routes as pulseRoutes } from "./pulse/routes";

export default [...pulseRoutes] satisfies RouteConfig;
