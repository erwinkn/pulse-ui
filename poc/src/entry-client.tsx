import { createRoot, hydrateRoot } from "react-dom/client";
import { App, getVdomForPath } from "./app";
import { getLoadedRegistry, loadRouteChunk } from "./router/loader";
import type { VdomNode } from "./vdom-renderer";

declare global {
	interface Window {
		__INITIAL_VDOM__?: VdomNode;
	}
}

async function main() {
	const pathname = window.location.pathname;
	const container = document.getElementById("root");

	if (!container) {
		throw new Error("Root container not found");
	}

	// Load required chunk before rendering to prevent hydration mismatch
	await loadRouteChunk(pathname);
	const registry = getLoadedRegistry();

	// Use SSR-provided VDOM if available, otherwise get from client-side map
	const vdom = window.__INITIAL_VDOM__ ?? getVdomForPath(pathname);

	const appElement = <App initialVdom={vdom} initialRegistry={registry} />;

	if (window.__INITIAL_VDOM__) {
		// SSR: hydrate existing HTML
		hydrateRoot(container, appElement);
	} else {
		// Client-only: create new root
		createRoot(container).render(appElement);
	}
}

main();
