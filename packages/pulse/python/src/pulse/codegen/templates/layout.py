from mako.template import Template

LAYOUT_TEMPLATE = Template(
	"""import {
  PulseApp as PulseAppShell,
  type PulseConfig,
  type PulsePrerender,
} from "pulse-ui-client";
import { pulseRouteTree, routeLoaders } from "./routes";

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

export function PulseApp({ prerender, url }: { prerender: PulsePrerender; url?: string }) {
  return (
    <PulseAppShell
      routes={pulseRouteTree}
      routeLoaders={routeLoaders}
      config={config}
      prerender={prerender}
      url={url}
    />
  );
}
"""
)
