import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { PulseSocketIOClient } from "../client";
import { InMemoryOfflineCache } from "../offline-cache";

describe("Offline Navigation Integration", () => {
	let client: PulseSocketIOClient;
	let cache: InMemoryOfflineCache;

	beforeEach(() => {
		cache = new InMemoryOfflineCache();
		const mockNavigate = (() => {}) as any;
		client = new PulseSocketIOClient(
			"http://localhost:3000",
			{},
			mockNavigate,
			{
				initialConnectingDelay: 1000,
				initialErrorDelay: 3000,
				reconnectErrorDelay: 2000,
			},
			cache,
		);
	});

	afterEach(() => {
		client.disconnect();
	});

	it("provides offline navigation manager via getOfflineNavigation", () => {
		const offlineNav = client.getOfflineNavigation();
		expect(offlineNav).toBeDefined();
		expect(typeof offlineNav.isOffline).toBe("function");
		expect(typeof offlineNav.canNavigateOffline).toBe("function");
		expect(typeof offlineNav.cacheRoute).toBe("function");
	});

	it("offline navigation manager is connected to cache", () => {
		const offlineNav = client.getOfflineNavigation();
		const vdom = { tag: "div", props: {}, children: [] };
		const routeInfo = { pathname: "/test" };

		offlineNav.cacheRoute("/test", vdom, routeInfo);

		expect(cache.has("/test")).toBe(true);
		const cached = cache.get("/test");
		expect(cached?.vdom).toEqual(vdom);
		expect(cached?.routeInfo).toEqual(routeInfo);
	});

	it("offline navigation manager can retrieve cached routes", () => {
		const offlineNav = client.getOfflineNavigation();
		const vdom = { tag: "div", props: {}, children: [] };
		const routeInfo = { pathname: "/test" };

		offlineNav.cacheRoute("/test", vdom, routeInfo);
		const cached = offlineNav.getCachedRoute("/test");

		expect(cached).not.toBeNull();
		expect(cached?.vdom).toEqual(vdom);
		expect(cached?.routeInfo).toEqual(routeInfo);
	});

	it("tracks pending navigation across client lifecycle", () => {
		const offlineNav = client.getOfflineNavigation();

		offlineNav.recordPendingNavigation("/pending");
		expect(offlineNav.getPendingNavigation()).toBe("/pending");

		offlineNav.clearPendingNavigation();
		expect(offlineNav.getPendingNavigation()).toBeUndefined();
	});

	it("tracks last online path", () => {
		const offlineNav = client.getOfflineNavigation();

		offlineNav.recordLastOnlinePath("/home");
		expect(offlineNav.getLastOnlinePath()).toBe("/home");

		offlineNav.recordLastOnlinePath("/about");
		expect(offlineNav.getLastOnlinePath()).toBe("/about");
	});

	it("supports multiple routes cached simultaneously", () => {
		const offlineNav = client.getOfflineNavigation();
		const vdom1 = { tag: "div", props: {}, children: ["Route 1"] };
		const vdom2 = { tag: "div", props: {}, children: ["Route 2"] };
		const vdom3 = { tag: "div", props: {}, children: ["Route 3"] };

		offlineNav.cacheRoute("/route1", vdom1, { pathname: "/route1" });
		offlineNav.cacheRoute("/route2", vdom2, { pathname: "/route2" });
		offlineNav.cacheRoute("/route3", vdom3, { pathname: "/route3" });

		expect(offlineNav.getCachedRoute("/route1")).not.toBeNull();
		expect(offlineNav.getCachedRoute("/route2")).not.toBeNull();
		expect(offlineNav.getCachedRoute("/route3")).not.toBeNull();
	});
});
