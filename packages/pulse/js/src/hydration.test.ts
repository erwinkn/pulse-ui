import { afterEach, describe, expect, test } from "bun:test";
import { type ChangeEvent, createElement, useState } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { act } from "@testing-library/react";
import { preHydrationInputCaptureScript, replayPreHydrationInputs } from "./hydration";

function installCaptureScript() {
	// The inline script ships as a string in the SSR HTML.
	// biome-ignore lint/security/noGlobalEval: evaluating our own inline script
	(0, eval)(preHydrationInputCaptureScript);
}

function type(input: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
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

	test("is a no-op when installed twice", () => {
		installCaptureScript();
		const first = window.__PULSE_INPUT_CAPTURE__;
		installCaptureScript();
		expect(window.__PULSE_INPUT_CAPTURE__).toBe(first);
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

	test("replays textarea and select values", () => {
		installCaptureScript();
		const textarea = document.createElement("textarea");
		const select = document.createElement("select");
		for (const value of ["one", "two"]) {
			const option = document.createElement("option");
			option.value = value;
			option.textContent = value;
			select.appendChild(option);
		}
		document.body.append(textarea, select);

		type(textarea, "hello");
		type(select, "two");

		textarea.value = "";
		select.value = "one";
		replayPreHydrationInputs();

		expect(textarea.value).toBe("hello");
		expect(select.value).toBe("two");
	});

	test("ignores file inputs and is a no-op without the script", () => {
		installCaptureScript();
		const file = document.createElement("input");
		file.type = "file";
		document.body.append(file);
		file.dispatchEvent(new Event("input", { bubbles: true }));

		replayPreHydrationInputs();
		expect(window.__PULSE_INPUT_CAPTURE__).toBeUndefined();
		replayPreHydrationInputs();
	});

	test("drops disconnected elements that have no remounted match", () => {
		installCaptureScript();
		const input = document.createElement("input");
		input.placeholder = "gone";
		document.body.appendChild(input);
		type(input, "gone");
		input.remove();

		replayPreHydrationInputs();
		expect(window.__PULSE_INPUT_CAPTURE__).toBeUndefined();
	});

	test("replays onto a remounted input with the same fingerprint", () => {
		installCaptureScript();
		const input = document.createElement("input");
		input.placeholder = "name";
		document.body.appendChild(input);
		type(input, "Avery Smith");
		input.remove();

		const replacement = document.createElement("input");
		replacement.placeholder = "name";
		replacement.value = "Avery";
		document.body.appendChild(replacement);

		replayPreHydrationInputs();
		expect(replacement.value).toBe("Avery Smith");
		expect(window.__PULSE_INPUT_CAPTURE__).toBeUndefined();
	});
});

describe("replay through a hydrated React controlled input", () => {
	test("desyncs React's value tracker so onChange fires after hydrate", async () => {
		function Controlled({
			value,
			onChange,
		}: {
			value: string;
			onChange: (value: string) => void;
		}) {
			return createElement("input", {
				value,
				onChange: (event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value),
			});
		}

		const html = renderToString(createElement(Controlled, { value: "Avery", onChange() {} }));
		const container = document.createElement("div");
		container.innerHTML = html;
		document.body.appendChild(container);
		const input = container.querySelector("input");
		if (!input) throw new Error("expected SSR input");

		installCaptureScript();
		type(input, "Avery Smith");

		const seen: string[] = [];
		function Hydrated() {
			const [value, setValue] = useState("Avery");
			return createElement(Controlled, {
				value,
				onChange: (next) => {
					seen.push(next);
					setValue(next);
				},
			});
		}

		await act(async () => {
			hydrateRoot(container, createElement(Hydrated));
		});
		// React 19 may keep the typed DOM value; the tracker still matches it,
		// so a plain dispatch would be dropped. Replay must desync first.

		await act(async () => {
			replayPreHydrationInputs();
		});

		expect(input.value).toBe("Avery Smith");
		expect(seen).toEqual(["Avery Smith"]);
	});
});
