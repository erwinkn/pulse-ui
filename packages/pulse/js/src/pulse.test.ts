import { describe, expect, it } from "bun:test";
import type { ServerError } from "./messages";
import { reduceServerErrorOverlay } from "./pulse";

function makeError(code: ServerError["code"], message: string): ServerError {
	return { code, message };
}

describe("reduceServerErrorOverlay", () => {
	it("keeps the current error across vdom updates", () => {
		const current = makeError("callback", "callback failed");
		const next = reduceServerErrorOverlay(current, { type: "update" });
		expect(next).toBe(current);
	});

	it("clears the current error on init", () => {
		const current = makeError("render", "render failed");
		const next = reduceServerErrorOverlay(current, { type: "init" });
		expect(next).toBeNull();
	});

	it("replaces the current error when a newer one arrives", () => {
		const oldError = makeError("callback", "old");
		const newError = makeError("api", "new");
		const next = reduceServerErrorOverlay(oldError, {
			type: "error",
			error: newError,
		});
		expect(next).toEqual(newError);
	});
});
