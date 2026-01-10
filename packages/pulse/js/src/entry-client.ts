/**
 * Client entry point for Pulse applications.
 *
 * This module handles:
 * 1. Reading __PULSE_DATA__ injected by SSR
 * 2. Hydrating the React root
 * 3. Initializing WebSocket connection
 * 4. Setting up the Pulse client
 */

import { hydrateRoot } from "react-dom/client";
import type { NavigateFunction } from "react-router";
import type { RouteInfo, VDOM } from "./index";
import { PulseSocketIOClient, VDOMRenderer } from "./index";
import { defaultComponentRegistry } from "./server/render";

interface PulseHydrationData {
	vdom: VDOM;
	routeInfo: RouteInfo;
}

/**
 * Extract and parse __PULSE_DATA__ from script tag.
 * Returns null if not found (client-only mode).
 */
function getHydrationData(): PulseHydrationData | null {
	const script = document.getElementById("__PULSE_DATA__");
	if (!script || !script.textContent) {
		return null;
	}

	try {
		const parsed = JSON.parse(script.textContent);
		return parsed as PulseHydrationData;
	} catch (err) {
		console.error("[Pulse] Failed to parse __PULSE_DATA__:", err);
		return null;
	}
}

/**
 * Initialize and mount Pulse application.
 */
async function main() {
	const container = document.getElementById("root");
	if (!container) {
		throw new Error("[Pulse] Root container not found");
	}

	const hydrateData = getHydrationData();

	// Create navigate function for client-side navigation
	const navigate: NavigateFunction = ((to: any, options?: any) => {
		if (typeof to === "number") {
			window.history.go(to);
		} else if (typeof to === "string") {
			if (options?.replace) {
				window.location.replace(to);
			} else {
				window.location.href = to;
			}
		}
	}) as unknown as NavigateFunction;

	// Create Pulse client
	const serverUrl = import.meta.env.VITE_PULSE_SERVER_URL || "/";
	const client = new PulseSocketIOClient(serverUrl, {}, navigate, {
		initialConnectingDelay: 1000,
		initialErrorDelay: 2000,
		reconnectErrorDelay: 1000,
	});

	if (hydrateData) {
		// SSR mode: hydrate with prerendered VDOM
		const renderer = new VDOMRenderer(client, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(hydrateData.vdom);

		hydrateRoot(container, reactTree);
		client.attach("/", {
			routeInfo: hydrateData.routeInfo,
			onInit: () => {},
			onUpdate: () => {},
			onJsExec: () => {},
			onServerError: () => {},
		});
	} else {
		// Client-only mode: create new root
		// TODO: implement client-only initialization
		throw new Error("[Pulse] Client-only mode not yet implemented");
	}

	// Connect to server
	await client.connect();
}

// Initialize when DOM is ready
if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", () => {
		void main();
	});
} else {
	void main();
}
