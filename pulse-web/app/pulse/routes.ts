import {
  type RouteConfig,
  route,
  layout,
  index,
} from "@react-router/dev/routes";

export const routes = [
  layout("pulse/_layout.tsx", [
    layout("pulse/layouts/_layout.tsx", [
      index("pulse/routes/index.tsx"),
      route("about", "pulse/routes/about.tsx"),
      route("counter", "pulse/routes/counter.tsx", [
        route("details", "pulse/routes/counter/details.tsx"),
      ]),
      route("components", "pulse/routes/components.tsx"),
      route("query", "pulse/routes/query.tsx"),
      route("dynamic/:route_id/:optional_segment?/*", "pulse/routes/dynamic/:route_id/:optional_segment^/*.tsx"),
    ]),
  ]),
] satisfies RouteConfig;
