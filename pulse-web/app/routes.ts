import {
  type RouteConfig,
  index,
  route,
  layout,
} from "@react-router/dev/routes";
import { routes as pulseRoutes } from "./pulse/routes";

export default [
  layout("pulse/_layout.tsx", [
    layout("pulse/layouts/_layout.tsx", [
      index("pulse/routes/index.tsx"),
      route("about", "pulse/routes/about.tsx"),
      route("counter", "pulse/routes/counter.tsx", [
        route("details", "pulse/routes/counter/details.tsx"),
      ]),
    ]),
    route("/counter-ssr", "routes/counter-ssr.tsx"),
  ]),
] satisfies RouteConfig;
