import { type RouteModule, routeLoaders } from "../routes";
import type { ComponentRegistry } from "../vdom-renderer";

/** Cache of loaded route modules to avoid re-fetching */
const moduleCache = new Map<string, RouteModule>();

/**
 * Load a route chunk dynamically with caching.
 * @param pattern - The route pattern (e.g., "/", "/dashboard")
 * @returns The loaded route module
 * @throws Error if no loader exists for the pattern
 */
export async function loadRouteChunk(pattern: string): Promise<RouteModule> {
	const cached = moduleCache.get(pattern);
	if (cached) {
		return cached;
	}

	const loader = routeLoaders[pattern];
	if (!loader) {
		throw new Error(`No loader exists for route: ${pattern}`);
	}

	const module = await loader();
	moduleCache.set(pattern, module);
	return module;
}

/**
 * Get a merged registry of all currently loaded route modules.
 * @returns Combined ComponentRegistry from all loaded chunks
 */
export function getLoadedRegistry(): ComponentRegistry {
	const merged: ComponentRegistry = {};
	for (const module of moduleCache.values()) {
		Object.assign(merged, module.registry);
	}
	return merged;
}
