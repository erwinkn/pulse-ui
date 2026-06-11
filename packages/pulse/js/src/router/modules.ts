/**
 * Route module loading + caching.
 *
 * Modules are cached by route id, keyed to the loader function that produced
 * them: when codegen or HMR swaps the loader map, stale entries reload
 * transparently. Loading is observable so the router re-renders when a module
 * arrives (e.g. after an HMR invalidation).
 */
import type { ComponentType } from "react";
import { matchRoutes, type PulseRoute } from "./match";

export type RouteModule = {
	default: ComponentType<any>;
	registry?: Record<string, unknown>;
	path?: string;
};

export type RouteLoader = () => Promise<RouteModule>;
export type RouteLoaderMap = Record<string, RouteLoader>;

type CacheEntry = {
	loader: RouteLoader;
	module?: RouteModule;
	promise?: Promise<RouteModule>;
};

const cache = new Map<string, CacheEntry>();
const listeners = new Set<() => void>();
let version = 0;

function notify() {
	version += 1;
	for (const listener of listeners) {
		listener();
	}
}

export function subscribeRouteModules(listener: () => void): () => void {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

export function getRouteModulesVersion(): number {
	return version;
}

export function getRouteModule(id: string, loaders: RouteLoaderMap): RouteModule | null {
	const entry = cache.get(id);
	if (entry && entry.loader === loaders[id] && entry.module) {
		return entry.module;
	}
	return null;
}

export function loadRouteModule(id: string, loaders: RouteLoaderMap): Promise<RouteModule> {
	const loader = loaders[id];
	if (!loader) {
		return Promise.reject(new Error(`[Pulse] No route loader registered for '${id}'`));
	}
	const entry = cache.get(id);
	if (entry && entry.loader === loader) {
		if (entry.module) return Promise.resolve(entry.module);
		if (entry.promise) return entry.promise;
	}
	const next: CacheEntry = { loader };
	next.promise = loader().then(
		(mod) => {
			// A newer loader may have replaced this entry while loading.
			if (cache.get(id) === next) {
				next.module = mod;
				next.promise = undefined;
				notify();
			}
			return mod;
		},
		(error) => {
			if (cache.get(id) === next) {
				cache.delete(id);
			}
			throw error;
		},
	);
	cache.set(id, next);
	return next.promise;
}

export async function preloadRoutesForPath(
	routes: PulseRoute[],
	loaders: RouteLoaderMap,
	pathname: string,
): Promise<void> {
	const match = matchRoutes(routes, pathname);
	if (!match) {
		return;
	}
	await Promise.all(match.matches.map((route) => loadRouteModule(route.id, loaders)));
}

export function prefetchRouteModules(
	routes: PulseRoute[],
	loaders: RouteLoaderMap,
	pathname: string,
): void {
	const match = matchRoutes(routes, pathname);
	if (!match) {
		return;
	}
	for (const route of match.matches) {
		loadRouteModule(route.id, loaders).catch((error) => {
			console.error(`[Pulse] Failed to prefetch route module '${route.id}':`, error);
		});
	}
}
