from mako.template import Template

LAYOUT_TEMPLATE = Template(
    """import { extractServerRouteInfo, PulseProvider, type PulseConfig, type PulsePrerender } from "pulse-ui-client";
import { Outlet, data, type LoaderFunctionArgs, type ClientLoaderFunctionArgs } from "react-router";
import { matchRoutes } from "react-router";
import { rrPulseRouteTree } from "./routes.runtime";
import { useLoaderData } from "react-router";

// This config is used to initialize the client
export const config: PulseConfig = {
  serverAddress: "${server_address}",
};


// Server loader: perform initial prerender, abort on first redirect/not-found
export async function loader(args: LoaderFunctionArgs) {
  const url = new URL(args.request.url);
  const matches = matchRoutes(rrPulseRouteTree, url.pathname) ?? [];
  const paths = matches.map(m => m.route.uniquePath);
  // Build minimal, safe headers for cross-origin API call
  const incoming = args.request.headers;
  const fwd = new Headers();
  const cookie = incoming.get("cookie");
  const authorization = incoming.get("authorization");
  if (cookie) fwd.set("cookie", cookie);
  if (authorization) fwd.set("authorization", authorization);
  fwd.set("content-type", "application/json");
  const res = await fetch("${internal_server_address}/prerender", {
    method: "POST",
    headers: fwd,
    body: JSON.stringify({ paths, routeInfo: extractServerRouteInfo(args) }),
  });
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  if (body.redirect) return new Response(null, { status: 302, headers: { Location: body.redirect } });
  if (body.notFound) return new Response(null, { status: 404 });
  const prerenderData = body as PulsePrerender;
  const setCookies =
    (res.headers.getSetCookie?.() as string[] | undefined) ??
    (res.headers.get("set-cookie") ? [res.headers.get("set-cookie") as string] : []);
  const headers = new Headers();
  for (const c of setCookies) headers.append("Set-Cookie", c);
  return data(prerenderData, { headers });
}

// Client loader: re-prerender on navigation while reusing renderId
export async function clientLoader(args: ClientLoaderFunctionArgs) {
  const url = new URL(args.request.url);
  const matches = matchRoutes(rrPulseRouteTree, url.pathname) ?? [];
  const paths = matches.map(m => m.route.uniquePath);
  const renderId = 
    typeof window !== "undefined" && typeof sessionStorage !== "undefined"
      ? (sessionStorage.getItem("__PULSE_RENDER_ID") ?? undefined) 
      : undefined;
  const res = await fetch("${server_address}/prerender", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ paths, routeInfo: extractServerRouteInfo(args), renderId }),
  });
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  if (body.redirect) return new Response(null, { status: 302, headers: { Location: body.redirect } });
  if (body.notFound) return new Response(null, { status: 404 });
  return body as PulsePrerender;
}

export default function PulseLayout() {
  const data = useLoaderData<typeof loader>();
  if (typeof window !== "undefined" && typeof sessionStorage !== "undefined") {
    sessionStorage.setItem("__PULSE_RENDER_ID", data.renderId);
  }
  return (
    <PulseProvider config={config} prerender={data}>
      <Outlet />
    </PulseProvider>
  );
}
// Persist renderId in sessionStorage for reuse in clientLoader is handled within the component
"""
)
