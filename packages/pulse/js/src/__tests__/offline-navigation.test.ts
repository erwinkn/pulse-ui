import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { InMemoryOfflineCache } from "../offline-cache";
import { OfflineNavigationManager } from "../offline-navigation";
import type { VDOM } from "../vdom";

describe("InMemoryOfflineCache", () => {
	let cache: InMemoryOfflineCache;

	beforeEach(() => {
		cache = new InMemoryOfflineCache(3);
	});

	it("stores and retrieves cached routes", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		const routeInfo = { pathname: "/test" };

		cache.set("/test", vdom, routeInfo);
		const cached = cache.get("/test");

		expect(cached).not.toBeNull();
		expect(cached?.vdom).toEqual(vdom);
		expect(cached?.routeInfo).toEqual(routeInfo);
	});

	it("returns null for non-existent routes", () => {
		expect(cache.get("/nonexistent")).toBeNull();
	});

	it("tracks whether a path exists", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		cache.set("/test", vdom, {});

		expect(cache.has("/test")).toBe(true);
		expect(cache.has("/other")).toBe(false);
	});

	it("lists all cached paths", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		cache.set("/path1", vdom, {});
		cache.set("/path2", vdom, {});
		cache.set("/path3", vdom, {});

		const paths = cache.getAllPaths();
		expect(paths).toContain("/path1");
		expect(paths).toContain("/path2");
		expect(paths).toContain("/path3");
	});

	it("evicts oldest entry when max size exceeded", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		cache.set("/path1", vdom, {});
		cache.set("/path2", vdom, {});
		cache.set("/path3", vdom, {});
		cache.set("/path4", vdom, {}); // Should evict /path1

		expect(cache.has("/path1")).toBe(false);
		expect(cache.has("/path2")).toBe(true);
		expect(cache.has("/path3")).toBe(true);
		expect(cache.has("/path4")).toBe(true);
	});

	it("clears all cached entries", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		cache.set("/path1", vdom, {});
		cache.set("/path2", vdom, {});

		cache.clear();

		expect(cache.has("/path1")).toBe(false);
		expect(cache.has("/path2")).toBe(false);
		expect(cache.getAllPaths()).toHaveLength(0);
	});

	it("stores timestamp with cached route", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		const before = Date.now();
		cache.set("/test", vdom, {});
		const after = Date.now();

		const cached = cache.get("/test");
		expect(cached?.timestamp).toBeGreaterThanOrEqual(before);
		expect(cached?.timestamp).toBeLessThanOrEqual(after);
	});
});

describe("OfflineNavigationManager", () => {
	let manager: OfflineNavigationManager;
	let cache: InMemoryOfflineCache;

	beforeEach(() => {
		cache = new InMemoryOfflineCache();
		manager = new OfflineNavigationManager({
			enabled: true,
			cache,
		});
	});

	afterEach(() => {
		manager.dispose();
	});

	it("tracks offline status", () => {
		expect(manager.isOffline()).toBe(!navigator.onLine);
	});

	it("determines if offline navigation is possible", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		manager.cacheRoute("/test", vdom, {});

		// Can only navigate offline if actually offline
		const canNavigate = manager.canNavigateOffline("/test");
		const isOffline = manager.isOffline();

		if (isOffline) {
			expect(canNavigate).toBe(true);
		}
	});

	it("returns false for uncached routes during offline navigation", () => {
		// Uncached routes cannot be navigated to offline, even if offline
		expect(manager.canNavigateOffline("/uncached")).toBe(false);
	});

	it("caches route information", () => {
		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		const routeInfo = { pathname: "/test" };

		manager.cacheRoute("/test", vdom, routeInfo);
		const cached = manager.getCachedRoute("/test");

		expect(cached).not.toBeNull();
		expect(cached?.vdom).toEqual(vdom);
	});

	it("tracks pending navigation", () => {
		manager.recordPendingNavigation("/test");
		expect(manager.getPendingNavigation()).toBe("/test");

		manager.clearPendingNavigation();
		expect(manager.getPendingNavigation()).toBeUndefined();
	});

	it("tracks last online path", () => {
		manager.recordLastOnlinePath("/previous");
		expect(manager.getLastOnlinePath()).toBe("/previous");
	});

	it("respects enabled flag", () => {
		const disabledManager = new OfflineNavigationManager({
			enabled: false,
			cache,
		});

		const vdom: VDOM = { tag: "div", props: {}, children: [] };
		disabledManager.cacheRoute("/test", vdom, {});

		// Cache should be empty when disabled
		expect(disabledManager.getCachedRoute("/test")).toBeNull();

		disabledManager.dispose();
	});
});
