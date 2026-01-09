import { describe, expect, it } from "bun:test";
import { matchPath } from "./match";

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
});
