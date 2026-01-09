import { renderToString } from "react-dom/server";
import { VDOMRenderer } from "../renderer";
import {
	type Location,
	type NavigateFn,
	type Params,
	PulseRouterProvider,
} from "../router/context";
import type { ComponentRegistry, VDOM } from "../vdom";

/**
 * Route information for SSR rendering.
 */
export interface RouteInfo {
	location: Location;
	params: Params;
}

/**
 * Configuration for renderVdom.
 */
export interface RenderConfig {
	routeInfo?: RouteInfo;
	registry?: ComponentRegistry;
}

// No-op navigate function for SSR (navigation happens on the client)
const ssrNavigate: NavigateFn = (() => {}) as NavigateFn;

/**
 * Renders VDOM JSON to an HTML string for SSR.
 * Wraps with PulseRouterProvider if routeInfo is provided.
 */
export function renderVdom(vdom: VDOM, config: RenderConfig = {}): string {
	// Create a minimal mock client for SSR (callbacks are not invoked server-side)
	const mockClient = {
		invokeCallback: () => {},
	} as any;

	const renderer = new VDOMRenderer(mockClient, "", config.registry ?? {});
	const reactTree = renderer.renderNode(vdom);

	// Wrap with router provider if route info is provided
	if (config.routeInfo) {
		const wrapped = (
			<PulseRouterProvider
				location={config.routeInfo.location}
				params={config.routeInfo.params}
				navigate={ssrNavigate}
			>
				{reactTree}
			</PulseRouterProvider>
		);
		return renderToString(wrapped);
	}

	return renderToString(reactTree);
}
