import { type RouteConfig, index, route } from "@react-router/dev/routes";
import { routes } from "./pulse/routes";

export default [...routes] satisfies RouteConfig;
