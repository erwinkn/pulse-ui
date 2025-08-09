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
      route("login", "pulse/routes/login.tsx"),
      route("secret", "pulse/routes/secret.tsx"),
    ]),
  ]),
] satisfies RouteConfig;
