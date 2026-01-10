import type { CachedRoute, OfflineCache } from "./offline-cache";
import type { VDOM } from "./vdom";

export interface OfflineNavigationConfig {
	enabled: boolean;
	cache: OfflineCache;
}

export interface OfflineNavigationState {
	isOffline: boolean;
	lastOnlinePath?: string;
	pendingNavigation?: string;
}

/**
 * Manages offline navigation using cached VDOM data.
 * When the connection is lost, allows navigation using previously cached routes.
 * On reconnection, syncs with server and reestablishes proper session.
 */
export class OfflineNavigationManager {
	#config: OfflineNavigationConfig;
	#state: OfflineNavigationState = {
		isOffline: false,
	};

	constructor(config: OfflineNavigationConfig) {
		this.#config = config;
		// Initialize offline state based on network connectivity
		this.#updateOnlineStatus();
		window.addEventListener("online", () => this.#handleOnline());
		window.addEventListener("offline", () => this.#handleOffline());
	}

	#updateOnlineStatus(): void {
		this.#state.isOffline = !navigator.onLine;
	}

	#handleOnline(): void {
		this.#state.isOffline = false;
	}

	#handleOffline(): void {
		this.#state.isOffline = true;
	}

	isOffline(): boolean {
		return this.#state.isOffline;
	}

	canNavigateOffline(pathname: string): boolean {
		if (!this.#config.enabled) return false;
		if (!this.#state.isOffline) return false;
		return this.#config.cache.has(pathname);
	}

	getCachedRoute(pathname: string): CachedRoute | null {
		if (!this.#config.enabled) return null;
		return this.#config.cache.get(pathname);
	}

	cacheRoute(pathname: string, vdom: VDOM, routeInfo: Record<string, any>): void {
		if (!this.#config.enabled) return;
		this.#config.cache.set(pathname, vdom, routeInfo);
	}

	recordPendingNavigation(pathname: string): void {
		this.#state.pendingNavigation = pathname;
	}

	getPendingNavigation(): string | undefined {
		return this.#state.pendingNavigation;
	}

	clearPendingNavigation(): void {
		this.#state.pendingNavigation = undefined;
	}

	recordLastOnlinePath(pathname: string): void {
		this.#state.lastOnlinePath = pathname;
	}

	getLastOnlinePath(): string | undefined {
		return this.#state.lastOnlinePath;
	}

	dispose(): void {
		window.removeEventListener("online", () => this.#handleOnline());
		window.removeEventListener("offline", () => this.#handleOffline());
	}
}
