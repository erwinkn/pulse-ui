import { type RouteConfig, index, route } from "@react-router/dev/routes";
import { routes } from "./pulse/routes";

export default [
  ...routes,
  
  // Manual test routes (not auto-generated)
  route("/test-updates", "routes/test-updates.tsx"),
] satisfies RouteConfig;
