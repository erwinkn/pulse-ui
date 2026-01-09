import type { ComponentRegistry } from "../vdom-renderer";

export interface RouteModule {
	path: string;
	registry: ComponentRegistry;
}

/** Dynamic imports for client-side code splitting (Vite async chunks) */
export const routeLoaders: Record<string, () => Promise<RouteModule>> = {
	"/": () => import("./home"),
	"/dashboard": () => import("./dashboard"),
	"/settings": () => import("./settings"),
};

/** Synchronous imports for SSR (Bun require) */
export const ssrRouteLoaders: Record<string, () => RouteModule> = {
	"/": () => require("./home"),
	"/dashboard": () => require("./dashboard"),
	"/settings": () => require("./settings"),
};
