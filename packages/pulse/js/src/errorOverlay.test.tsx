import { describe, expect, it, vi } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";
import {
	INITIAL_SERVER_ERROR_OVERLAY_STATE,
	reduceServerErrorOverlay,
	ServerErrorOverlay,
	type ServerErrorOverlayEntry,
} from "./errorOverlay";
import type { ServerError } from "./messages";

function makeError(
	code: ServerError["code"],
	message: string,
	stack?: string,
	details?: Record<string, any>,
): ServerError {
	return { code, message, stack, details };
}

function makeEntry(error: ServerError, repeatCount = 1): ServerErrorOverlayEntry {
	return {
		error,
		fingerprint: `${error.code}|${error.message}|${error.stack ?? ""}`,
		repeatCount,
		receivedAt: 1,
	};
}

describe("reduceServerErrorOverlay", () => {
	it("resets on init and keeps current on update", () => {
		const error = makeError("callback", "boom");
		const afterError = reduceServerErrorOverlay(INITIAL_SERVER_ERROR_OVERLAY_STATE, {
			type: "error",
			error,
		});
		expect(afterError.entries).toHaveLength(1);
		expect(afterError.isOpen).toBeTrue();

		const afterUpdate = reduceServerErrorOverlay(afterError, { type: "update" });
		expect(afterUpdate).toEqual(afterError);

		const reset = reduceServerErrorOverlay(afterUpdate, { type: "init" });
		expect(reset).toEqual(INITIAL_SERVER_ERROR_OVERLAY_STATE);
	});

	it("dedupes consecutive duplicates and reopens", () => {
		const error = makeError("api", "same", "stack line");
		const first = reduceServerErrorOverlay(INITIAL_SERVER_ERROR_OVERLAY_STATE, {
			type: "error",
			error,
		});
		const dismissed = reduceServerErrorOverlay(first, { type: "dismiss" });
		expect(dismissed.isOpen).toBeFalse();

		const second = reduceServerErrorOverlay(dismissed, { type: "error", error });
		expect(second.entries).toHaveLength(1);
		expect(second.entries[0]?.repeatCount).toBe(2);
		expect(second.isOpen).toBeTrue();
	});

	it("caps history and clamps navigation", () => {
		let state = INITIAL_SERVER_ERROR_OVERLAY_STATE;
		for (let i = 0; i < 30; i++) {
			state = reduceServerErrorOverlay(state, {
				type: "error",
				error: makeError("render", `err-${i}`),
			});
		}
		expect(state.entries).toHaveLength(25);
		expect(state.activeIndex).toBe(24);

		state = reduceServerErrorOverlay(state, { type: "select", index: -100 });
		expect(state.activeIndex).toBe(0);
		state = reduceServerErrorOverlay(state, { type: "previous" });
		expect(state.activeIndex).toBe(0);
		state = reduceServerErrorOverlay(state, { type: "select", index: 999 });
		expect(state.activeIndex).toBe(24);
		state = reduceServerErrorOverlay(state, { type: "next" });
		expect(state.activeIndex).toBe(24);
	});
});

describe("ServerErrorOverlay", () => {
	it("closes via close button, backdrop, and escape", () => {
		const close = vi.fn();
		const entry = makeEntry(makeError("callback", "message"));
		render(<ServerErrorOverlay entry={entry} activeIndex={0} errorCount={1} onClose={close} />);

		fireEvent.click(screen.getByRole("button", { name: "Close error overlay" }));
		expect(close).toHaveBeenCalledTimes(1);

		fireEvent.mouseDown(screen.getByTestId("server-error-overlay-backdrop"));
		expect(close).toHaveBeenCalledTimes(2);

		fireEvent.keyDown(window, { key: "Escape" });
		expect(close).toHaveBeenCalledTimes(3);
	});

	it("navigates entries and does not close on inside click", () => {
		const close = vi.fn();
		const prev = vi.fn();
		const next = vi.fn();
		const entry = makeEntry(makeError("callback", "message"));
		render(
			<ServerErrorOverlay
				entry={entry}
				activeIndex={1}
				errorCount={3}
				onClose={close}
				onPrevious={prev}
				onNext={next}
			/>,
		);

		expect(screen.getByText("2 of 3")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Prev" }));
		fireEvent.click(screen.getByRole("button", { name: "Next" }));
		expect(prev).toHaveBeenCalledTimes(1);
		expect(next).toHaveBeenCalledTimes(1);

		fireEvent.mouseDown(screen.getByTestId("server-error-overlay-panel"));
		expect(close).not.toHaveBeenCalled();
	});

	it("expands long message and stack and toggles internal frames", () => {
		const longMessage = "A".repeat(700);
		const longStackLines = [
			"Error: boom",
			"at App (src/App.tsx:1:1)",
			"at node_modules/pkg/index.js:1:1",
			...Array.from({ length: 30 }, (_, i) => `at frame-${i} (src/file-${i}.ts:1:1)`),
		].join("\n");

		const entry = makeEntry(makeError("render", longMessage, longStackLines));
		render(<ServerErrorOverlay entry={entry} activeIndex={0} errorCount={1} onClose={() => {}} />);

		fireEvent.click(screen.getByTestId("server-error-overlay-message-toggle"));
		expect(screen.getByRole("button", { name: "Show less" })).toBeInTheDocument();

		const stack = screen.getByTestId("server-error-overlay-stack");
		expect(stack).not.toHaveTextContent("at node_modules/pkg/index.js:1:1");

		fireEvent.click(screen.getByTestId("server-error-overlay-internal-toggle"));
		expect(stack).toHaveTextContent("at node_modules/pkg/index.js:1:1");

		fireEvent.click(screen.getByTestId("server-error-overlay-stack-toggle"));
		expect(stack).toHaveTextContent("at frame-20 (src/file-20.ts:1:1)");
	});

	it("copies full payload", async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(globalThis.navigator, "clipboard", {
			value: { writeText },
			configurable: true,
		});

		const entry = makeEntry(
			makeError("api", "copy me", "at one\nat two", {
				route: "/",
			}),
			2,
		);
		render(<ServerErrorOverlay entry={entry} activeIndex={0} errorCount={1} onClose={() => {}} />);

		fireEvent.click(screen.getByRole("button", { name: "Copy" }));
		expect(writeText).toHaveBeenCalledTimes(1);
		expect(writeText.mock.calls[0]?.[0]).toContain("Code: api");
		expect(writeText.mock.calls[0]?.[0]).toContain("Message: copy me");
		expect(writeText.mock.calls[0]?.[0]).toContain("Occurrences: 2");
	});
});
