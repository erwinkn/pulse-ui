import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/index.tsx"),
  route("/server-demo", "routes/server_demo.tsx"),
  route("/api-example", "routes/api_example.tsx"),
  route("/simple", "routes/simple.tsx"),
  route("/stateful-demo", "routes/stateful_demo.tsx"),
] satisfies RouteConfig;
