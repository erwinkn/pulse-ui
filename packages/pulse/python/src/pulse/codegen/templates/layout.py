from mako.template import Template

LAYOUT_TEMPLATE = Template(
	"""import { useEffect } from "react";
import { deserialize, extractServerRouteInfo, PulseProvider, type Directives, type PulseConfig, type PulsePrerender } from "pulse-ui-client";
import { Outlet, data, type LoaderFunctionArgs, type ClientLoaderFunctionArgs } from "react-router";
import { matchRoutes } from "react-router";
import { rrPulseRouteTree } from "./routes.runtime";
import { useLoaderData } from "react-router";

export const config: PulseConfig = {
  connectionStatus: {
    initialConnectingDelay: ${int(connection_status.initial_connecting_delay * 1000)},
    initialErrorDelay: ${int(connection_status.initial_error_delay * 1000)},
    reconnectErrorDelay: ${int(connection_status.reconnect_error_delay * 1000)},
  },
};

const PULSE_PRERENDER_PATH = "/_pulse/prerender";
const PULSE_DIRECTIVES_KEY = "__PULSE_DIRECTIVES";

function loadDirectives(): Directives {
  if (typeof sessionStorage === "undefined") return {};
  const value = sessionStorage.getItem(PULSE_DIRECTIVES_KEY);
  if (!value) return {};
  try {
    return JSON.parse(value) as Directives;
  } catch {
    sessionStorage.removeItem(PULSE_DIRECTIVES_KEY);
    return {};
  }
}


// Server loader: perform initial prerender, abort on first redirect/not-found
export async function loader(args: LoaderFunctionArgs) {
  const url = new URL(args.request.url);
  const matches = matchRoutes(rrPulseRouteTree, url.pathname) ?? [];
  const paths = matches.map(m => m.route.uniquePath);
  // Build minimal, safe headers for the private backend request.
  const incoming = args.request.headers;
  const fwd = new Headers();
  const cookie = incoming.get("cookie");
  const authorization = incoming.get("authorization");
  if (cookie) fwd.set("cookie", cookie);
  if (authorization) fwd.set("authorization", authorization);
  fwd.set("content-type", "application/json");
  const internalServerAddress = process.env.PULSE_SSR_BACKEND_URL;
  if (!internalServerAddress) {
    throw new Error("PULSE_SSR_BACKEND_URL is required for Pulse server rendering");
  }
  const res = await fetch(new URL(PULSE_PRERENDER_PATH, internalServerAddress), {
    method: "POST",
    headers: fwd,
    body: JSON.stringify({ paths, routeInfo: extractServerRouteInfo(args) }),
  });
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  if (body.redirect) return new Response(null, { status: 302, headers: { Location: body.redirect } });
  if (body.notFound) {
    console.error("Not found:", url.pathname);
    throw new Response("Not Found", { status: 404 });
  }
  const prerenderData = deserialize(body) as PulsePrerender;
  const setCookies =
    (res.headers.getSetCookie?.() as string[] | undefined) ??
    (res.headers.get("set-cookie") ? [res.headers.get("set-cookie") as string] : []);
  const headers = new Headers();
  for (const c of setCookies) headers.append("Set-Cookie", c);
  return data(prerenderData, { headers });
}

// Client loader: re-prerender on navigation while reusing directives
export async function clientLoader(args: ClientLoaderFunctionArgs) {
  const url = new URL(args.request.url);
  const matches = matchRoutes(rrPulseRouteTree, url.pathname) ?? [];
  const paths = matches.map(m => m.route.uniquePath);
  const directives = loadDirectives();
  const headers = new Headers({ "content-type": "application/json" });
  if (directives?.headers) {
    for (const [key, value] of Object.entries(directives.headers)) {
      headers.set(key, value as string);
    }
  }
  headers.set("x-pulse-client-loader", "1");
  const query = new URLSearchParams();
  if (directives?.query) {
    for (const [key, value] of Object.entries(directives.query)) {
      query.set(key, value as string);
    }
  }
  const queryString = query.toString();
  const prerenderUrl = `$${"{"}PULSE_PRERENDER_PATH}$${"{"}queryString ? `?$${"{"}queryString}` : ""}`;
  const res = await fetch(prerenderUrl, {
    method: "POST",
    headers,
    credentials: "same-origin",
    redirect: "manual",
    body: JSON.stringify({ paths, routeInfo: extractServerRouteInfo(args) }),
  });
  if (res.status === 409) {
    window.location.assign(args.request.url);
    throw new Error("Reloading due to stale Pulse deployment affinity.");
  }
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  if (body.redirect) return new Response(null, { status: 302, headers: { Location: body.redirect } });
  if (body.notFound) throw new Response("Not Found", { status: 404 });
  const prerenderData = deserialize(body) as PulsePrerender;
  if (typeof window !== "undefined" && typeof sessionStorage !== "undefined" && prerenderData.directives) {
    sessionStorage.setItem(PULSE_DIRECTIVES_KEY, JSON.stringify(prerenderData.directives));
  }
  return prerenderData as PulsePrerender;
}

export default function PulseLayout() {
  const data = useLoaderData<typeof loader>();
  useEffect(() => {
    sessionStorage.setItem(PULSE_DIRECTIVES_KEY, JSON.stringify(data.directives));
  }, [data.directives]);
  return (
    <PulseProvider config={config} prerender={data}>
      <Outlet />
    </PulseProvider>
  );
}
"""
)
