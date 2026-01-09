import { describe, expect, it } from "bun:test";
import { compareRoutes, matchPath, selectBestMatch } from "./match";

describe("matchPath", () => {
	describe("static paths", () => {
		it("matches exact static paths", () => {
			expect(matchPath("/users", "/users")).toEqual({
				matched: true,
				params: {},
			});
		});

		it("returns false for non-matching static paths", () => {
			expect(matchPath("/users", "/posts")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("normalizes trailing slashes", () => {
			expect(matchPath("/users/", "/users")).toEqual({
				matched: true,
				params: {},
			});
			expect(matchPath("/users", "/users/")).toEqual({
				matched: true,
				params: {},
			});
		});

		it("matches root path", () => {
			expect(matchPath("/", "/")).toEqual({
				matched: true,
				params: {},
			});
		});
	});

	describe("dynamic params", () => {
		it("matches single dynamic param", () => {
			expect(matchPath("/users/:id", "/users/123")).toEqual({
				matched: true,
				params: { id: "123" },
			});
		});

		it("matches multiple dynamic params", () => {
			expect(matchPath("/users/:userId/posts/:postId", "/users/1/posts/2")).toEqual({
				matched: true,
				params: { userId: "1", postId: "2" },
			});
		});

		it("returns false when missing required param segment", () => {
			expect(matchPath("/users/:id", "/users")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("returns false when path has extra segments", () => {
			expect(matchPath("/users/:id", "/users/123/extra")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("matches mixed static and dynamic segments", () => {
			expect(matchPath("/api/users/:id/profile", "/api/users/456/profile")).toEqual({
				matched: true,
				params: { id: "456" },
			});
		});

		it("returns false when static segment doesn't match", () => {
			expect(matchPath("/users/:id/posts", "/users/123/comments")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("handles param values with special characters", () => {
			expect(matchPath("/files/:name", "/files/my-file_2024.txt")).toEqual({
				matched: true,
				params: { name: "my-file_2024.txt" },
			});
		});
	});

	describe("optional params", () => {
		it("matches when optional param is missing", () => {
			expect(matchPath("/users/:id?", "/users")).toEqual({
				matched: true,
				params: { id: undefined },
			});
		});

		it("matches when optional param is provided", () => {
			expect(matchPath("/users/:id?", "/users/123")).toEqual({
				matched: true,
				params: { id: "123" },
			});
		});

		it("matches multiple optional params - none provided", () => {
			expect(matchPath("/a/:b?/:c?", "/a")).toEqual({
				matched: true,
				params: { b: undefined, c: undefined },
			});
		});

		it("matches multiple optional params - first provided", () => {
			expect(matchPath("/a/:b?/:c?", "/a/1")).toEqual({
				matched: true,
				params: { b: "1", c: undefined },
			});
		});

		it("matches multiple optional params - both provided", () => {
			expect(matchPath("/a/:b?/:c?", "/a/1/2")).toEqual({
				matched: true,
				params: { b: "1", c: "2" },
			});
		});

		it("returns false when path has more segments than pattern", () => {
			expect(matchPath("/users/:id?", "/users/123/extra")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("matches mixed required and optional params", () => {
			expect(matchPath("/users/:id/posts/:postId?", "/users/1/posts")).toEqual({
				matched: true,
				params: { id: "1", postId: undefined },
			});
			expect(matchPath("/users/:id/posts/:postId?", "/users/1/posts/2")).toEqual({
				matched: true,
				params: { id: "1", postId: "2" },
			});
		});

		it("returns false when required param is missing", () => {
			expect(matchPath("/users/:id/posts/:postId?", "/users")).toEqual({
				matched: false,
				params: {},
			});
		});
	});

	describe("catch-all (*)", () => {
		it("matches catch-all with multiple segments", () => {
			expect(matchPath("/files/*", "/files/a/b/c")).toEqual({
				matched: true,
				params: { "*": ["a", "b", "c"] },
			});
		});

		it("matches catch-all with no remaining segments", () => {
			expect(matchPath("/files/*", "/files")).toEqual({
				matched: true,
				params: { "*": [] },
			});
		});

		it("matches catch-all with single segment", () => {
			expect(matchPath("/files/*", "/files/readme.txt")).toEqual({
				matched: true,
				params: { "*": ["readme.txt"] },
			});
		});

		it("returns false when catch-all is not last segment", () => {
			expect(matchPath("/files/*/more", "/files/a/b/more")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("matches catch-all after dynamic param", () => {
			expect(matchPath("/users/:id/*", "/users/123/posts/456")).toEqual({
				matched: true,
				params: { id: "123", "*": ["posts", "456"] },
			});
		});

		it("returns false when prefix doesn't match", () => {
			expect(matchPath("/files/*", "/images/a/b")).toEqual({
				matched: false,
				params: {},
			});
		});

		it("matches root catch-all", () => {
			expect(matchPath("/*", "/any/path/here")).toEqual({
				matched: true,
				params: { "*": ["any", "path", "here"] },
			});
		});

		it("matches root catch-all with no segments", () => {
			expect(matchPath("/*", "/")).toEqual({
				matched: true,
				params: { "*": [] },
			});
		});
	});
});

describe("compareRoutes", () => {
	describe("static vs dynamic", () => {
		it("static beats dynamic", () => {
			expect(compareRoutes("/users/admin", "/users/:id")).toBe(-1);
		});

		it("dynamic loses to static", () => {
			expect(compareRoutes("/users/:id", "/users/admin")).toBe(1);
		});
	});

	describe("dynamic vs optional", () => {
		it("dynamic beats optional", () => {
			expect(compareRoutes("/users/:id", "/users/:id?")).toBe(-1);
		});

		it("optional loses to dynamic", () => {
			expect(compareRoutes("/users/:id?", "/users/:id")).toBe(1);
		});
	});

	describe("optional vs catch-all", () => {
		it("optional beats catch-all", () => {
			expect(compareRoutes("/files/:name?", "/files/*")).toBe(-1);
		});

		it("catch-all loses to optional", () => {
			expect(compareRoutes("/files/*", "/files/:name?")).toBe(1);
		});
	});

	describe("equal specificity", () => {
		it("equal static routes", () => {
			expect(compareRoutes("/users/admin", "/users/admin")).toBe(0);
		});

		it("equal dynamic routes", () => {
			expect(compareRoutes("/users/:id", "/users/:name")).toBe(0);
		});

		it("equal optional routes", () => {
			expect(compareRoutes("/users/:id?", "/users/:name?")).toBe(0);
		});
	});

	describe("multi-segment comparison", () => {
		it("compares segment by segment - first segment differs", () => {
			expect(compareRoutes("/users/admin/posts", "/users/:id/posts")).toBe(-1);
		});

		it("compares segment by segment - second segment differs", () => {
			expect(compareRoutes("/api/:version/users", "/api/:version/:resource")).toBe(-1);
		});
	});
});

describe("selectBestMatch", () => {
	it("returns most specific match", () => {
		const routes = [
			{ pattern: "/users/:id", name: "user-detail" },
			{ pattern: "/users/admin", name: "admin" },
			{ pattern: "/users/*", name: "catchall" },
		];

		const result = selectBestMatch(routes, "/users/admin");
		expect(result).not.toBeNull();
		expect(result!.route.name).toBe("admin");
		expect(result!.params).toEqual({});
	});

	it("returns dynamic match when no static match", () => {
		const routes = [
			{ pattern: "/users/:id", name: "user-detail" },
			{ pattern: "/users/admin", name: "admin" },
			{ pattern: "/users/*", name: "catchall" },
		];

		const result = selectBestMatch(routes, "/users/123");
		expect(result).not.toBeNull();
		expect(result!.route.name).toBe("user-detail");
		expect(result!.params).toEqual({ id: "123" });
	});

	it("returns catch-all when no other match", () => {
		const routes = [
			{ pattern: "/users/:id", name: "user-detail" },
			{ pattern: "/users/*", name: "catchall" },
		];

		const result = selectBestMatch(routes, "/users/123/posts/456");
		expect(result).not.toBeNull();
		expect(result!.route.name).toBe("catchall");
		expect(result!.params).toEqual({ "*": ["123", "posts", "456"] });
	});

	it("returns null when no match", () => {
		const routes = [
			{ pattern: "/users/:id", name: "user-detail" },
			{ pattern: "/posts/:id", name: "post-detail" },
		];

		const result = selectBestMatch(routes, "/comments/123");
		expect(result).toBeNull();
	});

	it("handles empty routes array", () => {
		const result = selectBestMatch([], "/any/path");
		expect(result).toBeNull();
	});

	it("includes params from matched route", () => {
		const routes = [{ pattern: "/users/:userId/posts/:postId", name: "user-post" }];

		const result = selectBestMatch(routes, "/users/1/posts/2");
		expect(result).not.toBeNull();
		expect(result!.params).toEqual({ userId: "1", postId: "2" });
	});

	it("prefers dynamic over optional", () => {
		const routes = [
			{ pattern: "/files/:name?", name: "optional" },
			{ pattern: "/files/:name", name: "required" },
		];

		const result = selectBestMatch(routes, "/files/readme.txt");
		expect(result).not.toBeNull();
		expect(result!.route.name).toBe("required");
	});
});
