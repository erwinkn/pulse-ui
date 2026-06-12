import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";

import { MantineProvider } from "@mantine/core";
import { deserialize, preloadRoutesForPath, type PulsePrerender } from "pulse-ui-client";
import { hydrateRoot } from "react-dom/client";
import { PulseApp } from "../app/pulse/_layout";
import { pulseRouteTree, routeLoaders } from "../app/pulse/routes";

declare global {
	interface Window {
		__PULSE_PRERENDER__?: unknown;
	}
}

async function main() {
	const container = document.getElementById("root");
	if (!container) {
		throw new Error("Root container not found");
	}

	const serialized = window.__PULSE_PRERENDER__;
	if (!serialized) {
		throw new Error("Missing Pulse prerender payload");
	}

	const prerender = deserialize(serialized) as PulsePrerender;
	await preloadRoutesForPath(pulseRouteTree, routeLoaders, window.location.pathname);

	const app = (
		<MantineProvider>
			<PulseApp prerender={prerender} url={window.location.href} />
		</MantineProvider>
	);
	hydrateRoot(container, app);
}

void main();
