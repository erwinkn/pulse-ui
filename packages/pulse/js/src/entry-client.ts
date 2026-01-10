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
import type { Directives } from "./client";
import type { ComponentRegistry, NavigateFn, RouteInfo, VDOM } from "./index";
import { PulseSocketIOClient, VDOMRenderer } from "./index";
import { defaultComponentRegistry, setClientNavigate } from "./server/render";

export interface PulseHydrationData {
	vdom: VDOM;
	routeInfo: RouteInfo;
	directives?: Directives;
}

export interface InitPulseClientOptions {
	/** WebSocket URL for Pulse server */
	wsUrl: string;
	/** Custom component registry (merged with defaults) */
	registry?: ComponentRegistry;
	/** Root element ID (default: "root") */
	rootId?: string;
}

/**
 * Extract and parse __PULSE_DATA__ from script tag.
 * Returns null if not found (client-only mode).
 *
 * Data format from SSR: [callbacks_array, {vdom, routeInfo}]
 */
export function getHydrationData(): PulseHydrationData | null {
	const script = document.getElementById("__PULSE_DATA__");
	if (!script || !script.textContent) {
		return null;
	}

	try {
		const parsed = JSON.parse(script.textContent);
		// SSR wraps data as [callbacks_array, {vdom, routeInfo}]
		if (Array.isArray(parsed) && parsed.length >= 2) {
			return parsed[1] as PulseHydrationData;
		}
		// Direct format fallback
		return parsed as PulseHydrationData;
	} catch (err) {
		console.error("[Pulse] Failed to parse __PULSE_DATA__:", err);
		return null;
	}
}

/**
 * Initialize and mount Pulse application.
 * Call this from your client entry point after DOM is ready.
 */
export async function initPulseClient(
	options: InitPulseClientOptions,
): Promise<PulseSocketIOClient> {
	const { wsUrl, registry = {}, rootId = "root" } = options;

	const container = document.getElementById(rootId);
	if (!container) {
		throw new Error(`[Pulse] Root container '${rootId}' not found`);
	}

	const hydrateData = getHydrationData();

	// Create navigate function for client-side navigation
	// Uses full page navigation to trigger SSR on target route
	// This ensures the server renders the new route content
	const navigate: NavigateFn = ((to: any, opts?: any) => {
		if (typeof to === "number") {
			window.history.go(to);
		} else if (typeof to === "string") {
			if (opts?.replace) {
				window.location.replace(to);
			} else {
				window.location.href = to;
			}
		}
	}) as unknown as NavigateFn;

	// Create Pulse client with directives from SSR data (if available)
	const directives = hydrateData?.directives ?? {};
	const client = new PulseSocketIOClient(wsUrl, directives, navigate, {
		initialConnectingDelay: 1000,
		initialErrorDelay: 2000,
		reconnectErrorDelay: 1000,
	});

	// Set the navigate function for the router context before hydration
	setClientNavigate(navigate);

	// Merge custom registry with defaults
	const componentRegistry = { ...defaultComponentRegistry, ...registry };

	if (hydrateData) {
		// SSR mode: hydrate with prerendered VDOM
		const renderer = new VDOMRenderer(client, "/", componentRegistry);
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

	return client;
}
