from mako.template import Template

LAYOUT_TEMPLATE = Template(
	"""import { useCallback, useEffect, useState } from "react";
import {
  buildRouteInfo,
  deserialize,
  PulseProvider,
  PulseRouterProvider,
  PulseRoutes,
  type PulseConfig,
  type PulsePrerender,
} from "pulse-ui-client";
import { pulseRouteTree, routeLoaders } from "./routes";

const DIRECTIVES_KEY = "__PULSE_DIRECTIVES";

// This config is used to initialize the client
export const config: PulseConfig = {
  serverAddress: "${server_address}",
  apiPrefix: "${api_prefix}",
  connectionStatus: {
    initialConnectingDelay: ${int(connection_status.initial_connecting_delay * 1000)},
    initialErrorDelay: ${int(connection_status.initial_error_delay * 1000)},
    reconnectErrorDelay: ${int(connection_status.reconnect_error_delay * 1000)},
  },
};

function readStoredDirectives(): any {
  if (typeof window === "undefined" || typeof sessionStorage === "undefined") {
    return {};
  }
  try {
    return JSON.parse(sessionStorage.getItem(DIRECTIVES_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function persistDirectives(prerender: PulsePrerender) {
  if (typeof window === "undefined" || typeof sessionStorage === "undefined") {
    return;
  }
  if (prerender.directives) {
    sessionStorage.setItem(DIRECTIVES_KEY, JSON.stringify(prerender.directives));
  }
}

async function fetchPrerender(paths: string[], routeInfo: any) {
  const directives = readStoredDirectives();
  const headers: HeadersInit = { "content-type": "application/json" };
  if (directives?.headers) {
    for (const [key, value] of Object.entries(directives.headers)) {
      headers[key] = value as string;
    }
  }
  const res = await fetch(config.serverAddress + config.apiPrefix + "/prerender", {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({ paths, routeInfo }),
  });
  if (!res.ok) throw new Error("Failed to prerender batch:" + res.status);
  const body = await res.json();
  return body;
}

export function PulseApp({ prerender, url }: { prerender: PulsePrerender; url?: string }) {
  const [current, setCurrent] = useState(prerender);

  useEffect(() => {
    persistDirectives(current);
  }, [current]);

  const handleNavigate = useCallback(
    async (target: { location: { pathname: string; search: string; hash: string }; match: any }) => {
      const paths = target.match.matches.map((route: any) => route.id);
      const routeInfo = buildRouteInfo(target.location, target.match.params, target.match.catchall);
      const body = await fetchPrerender(paths, routeInfo);
      if (body.redirect) {
        if (typeof window !== "undefined") {
          window.location.assign(body.redirect);
        }
        return;
      }
      if (body.notFound) {
        if (typeof window !== "undefined") {
          window.location.assign("/not-found");
        }
        return;
      }
      const next = deserialize(body) as PulsePrerender;
      setCurrent(next);
    },
    [],
  );

  return (
    <PulseRouterProvider routes={pulseRouteTree} routeLoaders={routeLoaders} initialUrl={url} onNavigate={handleNavigate}>
      <PulseProvider config={config} prerender={current}>
        <PulseRoutes />
      </PulseProvider>
    </PulseRouterProvider>
  );
}
"""
)
