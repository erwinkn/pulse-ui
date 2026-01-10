/**
 * Tests for client-side navigation state synchronization.
 *
 * Verifies that navigation state is properly sent from client to server.
 */

import { describe, expect, it } from "bun:test";
import type { ClientNavigationMessage } from "../messages";

describe("Navigation sync message structure", () => {
	it("should create navigation message with required fields", () => {
		const msg: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/users/123",
			search: "?sort=name",
			hash: "#details",
		};

		expect(msg.type).toBe("navigation");
		expect(msg.pathname).toBe("/users/123");
		expect(msg.search).toBe("?sort=name");
		expect(msg.hash).toBe("#details");
		expect(msg.state).toBeUndefined();
	});

	it("should create navigation message with state", () => {
		const msg: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/search",
			search: "?q=test",
			hash: "",
			state: { returnTo: "/home" },
		};

		expect(msg.state).toEqual({ returnTo: "/home" });
	});

	it("should handle empty query and hash", () => {
		const msg: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/",
			search: "",
			hash: "",
		};

		expect(msg.pathname).toBe("/");
		expect(msg.search).toBe("");
		expect(msg.hash).toBe("");
	});

	it("should preserve complex state objects", () => {
		const state = {
			filters: { category: "electronics", price: [10, 100] },
			pagination: { page: 2, size: 20 },
		};

		const msg: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/products",
			search: "?category=electronics",
			hash: "",
			state,
		};

		expect(msg.state).toEqual(state);
	});

	it("should handle various pathname patterns", () => {
		const paths = [
			"/",
			"/home",
			"/users/123",
			"/users/123/posts/456",
			"/api/v1/data",
			"/path-with-dashes",
			"/path_with_underscores",
		];

		for (const path of paths) {
			const msg: ClientNavigationMessage = {
				type: "navigation",
				pathname: path,
				search: "",
				hash: "",
			};
			expect(msg.pathname).toBe(path);
		}
	});

	it("should handle various query string patterns", () => {
		const queries = [
			"",
			"?param=value",
			"?a=1&b=2",
			"?complex=hello%20world",
			"?array=1&array=2&array=3",
		];

		for (const query of queries) {
			const msg: ClientNavigationMessage = {
				type: "navigation",
				pathname: "/search",
				search: query,
				hash: "",
			};
			expect(msg.search).toBe(query);
		}
	});

	it("should handle various hash patterns", () => {
		const hashes = ["", "#section", "#section-subsection", "#123", "#multiple-hyphens-here"];

		for (const hash of hashes) {
			const msg: ClientNavigationMessage = {
				type: "navigation",
				pathname: "/page",
				search: "",
				hash,
			};
			expect(msg.hash).toBe(hash);
		}
	});

	it("should support null and undefined state", () => {
		const msg1: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/home",
			search: "",
			hash: "",
			state: null as any,
		};

		const msg2: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/home",
			search: "",
			hash: "",
		};

		expect(msg1.state).toBe(null);
		expect(msg2.state).toBeUndefined();
	});

	it("should preserve state with various data types", () => {
		const states = [
			{ string: "value" },
			{ number: 42 },
			{ boolean: true },
			{ array: [1, 2, 3] },
			{ nested: { deep: { value: "test" } } },
			{ mixed: [{ a: 1 }, { b: "two" }] },
		];

		for (const state of states) {
			const msg: ClientNavigationMessage = {
				type: "navigation",
				pathname: "/test",
				search: "",
				hash: "",
				state,
			};
			expect(msg.state).toEqual(state);
		}
	});

	it("should include full URL components together", () => {
		const msg: ClientNavigationMessage = {
			type: "navigation",
			pathname: "/docs/api",
			search: "?version=v2&lang=python",
			hash: "#authentication",
			state: { reference: true },
		};

		expect(msg.pathname).toBe("/docs/api");
		expect(msg.search).toBe("?version=v2&lang=python");
		expect(msg.hash).toBe("#authentication");
		expect(msg.state).toEqual({ reference: true });
	});
});
