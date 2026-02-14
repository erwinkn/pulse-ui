import { describe, expect, it } from "bun:test";
import { INITIAL_SERVER_ERROR_OVERLAY_STATE, reduceServerErrorOverlay } from "./errorOverlay";
import type { ServerError } from "./messages";

function makeError(code: ServerError["code"], message: string): ServerError {
	return { code, message };
}

describe("PulseView error overlay reducer wiring", () => {
	it("keeps queue across vdom updates", () => {
		const withError = reduceServerErrorOverlay(INITIAL_SERVER_ERROR_OVERLAY_STATE, {
			type: "error",
			error: makeError("callback", "callback failed"),
		});
		const afterUpdate = reduceServerErrorOverlay(withError, { type: "update" });
		expect(afterUpdate).toEqual(withError);
	});

	it("clears queue on init", () => {
		const withError = reduceServerErrorOverlay(INITIAL_SERVER_ERROR_OVERLAY_STATE, {
			type: "error",
			error: makeError("render", "render failed"),
		});
		const cleared = reduceServerErrorOverlay(withError, { type: "init" });
		expect(cleared).toEqual(INITIAL_SERVER_ERROR_OVERLAY_STATE);
	});
});
