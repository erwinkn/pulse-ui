import { redirect, type LoaderFunctionArgs } from "react-router";
import { Link, Outlet } from "react-router";
import { extractServerRouteInfo } from "~/pulse-lib/messages";
import { PulseView } from "~/pulse-lib/pulse";
import type { ComponentRegistry, VDOM } from "~/pulse-lib/vdom";
import { config } from "~/pulse/_layout";

// Component registry
const externalComponents: ComponentRegistry = {
  Link: Link,
  Outlet: Outlet,
};

const path = "counter";

export async function loader(args: LoaderFunctionArgs) {
  const routeInfo = extractServerRouteInfo(args);
  const res = await fetch(config.serverAddress + "/prerender/" + path, {
    method: "POST",
    body: JSON.stringify(routeInfo),
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 404) {
    return redirect("/not-found");
  }
  if (res.status === 302 || res.status === 301) {
    const location = res.headers.get("Location");
    if (location) {
      return redirect(location);
    }
  }
  if (!res.ok) {
    throw new Error(
      `Failed to fetch prerender route /${path}: ${res.status} ${res.statusText}`
    );
  }
  const vdom = await res.json();
  return vdom;
}

export default function RouteComponent({ loaderData }: { loaderData: VDOM }) {
  return (
    <PulseView
      initialVDOM={loaderData}
      externalComponents={externalComponents}
      path={path}
    />
  );
}
