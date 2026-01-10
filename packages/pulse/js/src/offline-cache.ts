import type { VDOM } from "./vdom";

export interface CachedRoute {
	vdom: VDOM;
	timestamp: number;
	routeInfo: Record<string, any>;
}

export interface OfflineCache {
	get(pathname: string): CachedRoute | null;
	set(pathname: string, vdom: VDOM, routeInfo: Record<string, any>): void;
	clear(): void;
	has(pathname: string): boolean;
	getAllPaths(): string[];
}

/**
 * In-memory cache for VDOM and route info to support offline navigation.
 * Stores the last rendered state for each route to allow navigation
 * when the connection is offline.
 */
export class InMemoryOfflineCache implements OfflineCache {
	readonly #cache: Map<string, CachedRoute> = new Map();
	readonly #maxSize: number;

	constructor(maxSize = 50) {
		this.#maxSize = maxSize;
	}

	get(pathname: string): CachedRoute | null {
		return this.#cache.get(pathname) ?? null;
	}

	set(pathname: string, vdom: VDOM, routeInfo: Record<string, any>): void {
		// Simple LRU: if at capacity, remove oldest entry
		if (this.#cache.size >= this.#maxSize && !this.#cache.has(pathname)) {
			const oldestKey = this.#cache.keys().next().value;
			if (oldestKey) {
				this.#cache.delete(oldestKey);
			}
		}

		this.#cache.set(pathname, {
			vdom,
			timestamp: Date.now(),
			routeInfo,
		});
	}

	has(pathname: string): boolean {
		return this.#cache.has(pathname);
	}

	clear(): void {
		this.#cache.clear();
	}

	getAllPaths(): string[] {
		return Array.from(this.#cache.keys());
	}
}

/**
 * LocalStorage-based cache for persistence across sessions.
 * Stores serialized VDOM to browser localStorage.
 */
export class LocalStorageOfflineCache implements OfflineCache {
	readonly #storageKey = "__pulse_offline_cache__";

	private getData(): Map<string, CachedRoute> {
		try {
			const raw = localStorage.getItem(this.#storageKey);
			if (!raw) return new Map();
			const parsed = JSON.parse(raw) as Record<string, CachedRoute>;
			return new Map(Object.entries(parsed));
		} catch {
			return new Map();
		}
	}

	private saveData(data: Map<string, CachedRoute>): void {
		try {
			const obj = Object.fromEntries(data);
			localStorage.setItem(this.#storageKey, JSON.stringify(obj));
		} catch {
			// Silently fail if localStorage is full or unavailable
		}
	}

	get(pathname: string): CachedRoute | null {
		const data = this.getData();
		return data.get(pathname) ?? null;
	}

	set(pathname: string, vdom: VDOM, routeInfo: Record<string, any>): void {
		const data = this.getData();
		data.set(pathname, {
			vdom,
			timestamp: Date.now(),
			routeInfo,
		});
		this.saveData(data);
	}

	has(pathname: string): boolean {
		return this.getData().has(pathname);
	}

	clear(): void {
		localStorage.removeItem(this.#storageKey);
	}

	getAllPaths(): string[] {
		return Array.from(this.getData().keys());
	}
}
