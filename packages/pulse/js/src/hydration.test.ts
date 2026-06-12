import { afterEach, describe, expect, test } from "bun:test";
import { preHydrationInputCaptureScript, replayPreHydrationInputs } from "./hydration";

function installCaptureScript() {
	// The inline script ships as a string in the SSR document <head>.
	// biome-ignore lint/security/noGlobalEval: evaluating our own inline script
	(0, eval)(preHydrationInputCaptureScript);
}

function type(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
	input.value = value;
	input.dispatchEvent(new Event("input", { bubbles: true }));
}

afterEach(() => {
	window.__PULSE_INPUT_CAPTURE__?.stop();
	delete window.__PULSE_INPUT_CAPTURE__;
	document.body.innerHTML = "";
});

describe("pre-hydration input capture", () => {
	test("replays text typed before hydration reset it", () => {
		installCaptureScript();
		const input = document.createElement("input");
		document.body.appendChild(input);
		type(input, "Avery Smith");

		// Hydration: React resets the controlled input to its initial value.
		input.value = "Avery";

		const seen: string[] = [];
		input.addEventListener("input", () => seen.push(input.value));

		replayPreHydrationInputs();

		expect(input.value).toBe("Avery Smith");
		// The replay dispatched an input event so framework state catches up.
		expect(seen).toEqual(["Avery Smith"]);
		// Capture buffer is consumed.
		expect(window.__PULSE_INPUT_CAPTURE__).toBeUndefined();
	});

	test("keeps the latest value when typing continued", () => {
		installCaptureScript();
		const input = document.createElement("input");
		document.body.appendChild(input);
		type(input, "a");
		type(input, "ab");
		type(input, "abc");

		input.value = "";
		replayPreHydrationInputs();
		expect(input.value).toBe("abc");
	});

	test("dispatches even when the value still matches", () => {
		// Hydration may reset the input only on a later controlled render, so
		// the framework's state must adopt the value via the event regardless.
		installCaptureScript();
		const input = document.createElement("input");
		document.body.appendChild(input);
		type(input, "same");

		const seen: string[] = [];
		input.addEventListener("input", () => seen.push(input.value));
		replayPreHydrationInputs();

		expect(input.value).toBe("same");
		expect(seen).toEqual(["same"]);
	});

	test("restores checkbox state through click regardless of resets", () => {
		installCaptureScript();
		const box = document.createElement("input");
		box.type = "checkbox";
		document.body.appendChild(box);
		box.click(); // user checks it pre-hydration

		box.checked = false; // hydration reset
		replayPreHydrationInputs();
		expect(box.checked).toBe(true);
	});

	test("restores checkbox state when hydration did not reset it", () => {
		installCaptureScript();
		const box = document.createElement("input");
		box.type = "checkbox";
		document.body.appendChild(box);
		box.click();

		const seen: boolean[] = [];
		box.addEventListener("change", () => seen.push(box.checked));
		replayPreHydrationInputs();
		expect(box.checked).toBe(true);
		expect(seen).toEqual([true]);
	});

	test("ignores disconnected elements and is a no-op without the script", () => {
		installCaptureScript();
		const input = document.createElement("input");
		document.body.appendChild(input);
		type(input, "gone");
		input.remove();

		replayPreHydrationInputs();
		// Second call without capture installed: must not throw.
		replayPreHydrationInputs();
	});
});
