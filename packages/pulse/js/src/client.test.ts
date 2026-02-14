import { describe, expect, it } from "bun:test";
import { resolveServerErrorViewPath } from "./client";

describe("resolveServerErrorViewPath", () => {
	it("returns exact path matches", () => {
		expect(resolveServerErrorViewPath("/counter", ["/", "/counter"])).toBe("/counter");
	});

	it("normalizes trailing slashes", () => {
		expect(resolveServerErrorViewPath("/counter/", ["/", "/counter"])).toBe("/counter");
	});

	it("maps root path to empty active path when needed", () => {
		expect(resolveServerErrorViewPath("/", [""])).toBe("");
	});

	it("falls back to the only active view when path is missing", () => {
		expect(resolveServerErrorViewPath(undefined, ["/"])).toBe("/");
	});

	it("does not guess when multiple active views exist", () => {
		expect(resolveServerErrorViewPath(undefined, ["/", "/counter"])).toBeUndefined();
	});

	it("does not guess unmatched paths with multiple active views", () => {
		expect(resolveServerErrorViewPath("/missing", ["/", "/counter"])).toBeUndefined();
	});
});
