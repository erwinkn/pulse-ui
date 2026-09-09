/**
 * Pre-hydration input capture and replay.
 *
 * React never restores what a user typed into an SSR'd controlled input
 * before hydration: the controlled value prop overwrites the DOM value.
 * Pulse owns the SSR tree, so we record input/change from HTML parse
 * (inline script emitted by PulseProvider) and replay after the hydration
 * commit through native setters so React's onChange observes the edit.
 */

type CapturedEntry = { value: string } | { checked: boolean };

type CaptureHandle = {
	records: Map<Element, CapturedEntry>;
	stop: () => void;
};

declare global {
	interface Window {
		__PULSE_INPUT_CAPTURE__?: CaptureHandle;
	}
}

/**
 * Inline script for the SSR document. Must run before the user can
 * interact, so embed it directly:
 * `<script>${preHydrationInputCaptureScript}</script>`.
 */
export const preHydrationInputCaptureScript = `(function () {
	if (window.__PULSE_INPUT_CAPTURE__) return;
	var records = new Map();
	function record(event) {
		var t = event.target;
		if (!t || !t.tagName) return;
		var tag = t.tagName;
		if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") return;
		if (t.type === "file") return;
		if (t.type === "checkbox" || t.type === "radio") {
			records.set(t, { checked: t.checked });
		} else {
			records.set(t, { value: t.value });
		}
	}
	document.addEventListener("input", record, true);
	document.addEventListener("change", record, true);
	window.__PULSE_INPUT_CAPTURE__ = {
		records: records,
		stop: function () {
			document.removeEventListener("input", record, true);
			document.removeEventListener("change", record, true);
		},
	};
})();`;

/**
 * Replay inputs recorded before hydration. Safe to call more than once:
 * records are dropped as they are applied. A no-op when the capture script
 * is absent (client-only renders) or nothing was typed.
 *
 * Must run after Pulse views `attach`, otherwise `invokeCallback` drops the
 * synthetic events. React may also replace the SSR node during hydrate —
 * resolve a live match by tag/type/name/id/placeholder when that happens.
 */
export function replayPreHydrationInputs(): void {
	if (typeof window === "undefined") return;
	const capture = window.__PULSE_INPUT_CAPTURE__;
	if (!capture) return;
	capture.stop();

	// Always dispatch, even when the DOM value still matches: hydration may
	// not have reset the input yet, and only the event makes the framework's
	// state adopt the value (otherwise the next controlled render reverts it).
	for (const [element, entry] of [...capture.records]) {
		const target = resolveReplayTarget(element);
		if (!target) {
			capture.records.delete(element);
			continue;
		}

		if ("checked" in entry) {
			const input = target as HTMLInputElement;
			// Force the opposite state through React's tracked instance setter
			// (hydration initialized the tracker with the user's state, so a
			// click alone would be deduped as a no-op), then click() to toggle
			// back through React's event system.
			setDesyncingReactTracker(input, "checked", !entry.checked);
			input.click();
			capture.records.delete(element);
			continue;
		}

		const control = target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
		if (!setDesyncingReactTracker(control, "value", entry.value)) continue;
		control.dispatchEvent(new Event("input", { bubbles: true }));
		control.dispatchEvent(new Event("change", { bubbles: true }));
		if (document.activeElement === control && "setSelectionRange" in control) {
			try {
				control.setSelectionRange(entry.value.length, entry.value.length);
			} catch {
				// Some input types (email, number) don't support selection.
			}
		}
		capture.records.delete(element);
	}

	if (capture.records.size === 0) {
		delete window.__PULSE_INPUT_CAPTURE__;
	}
}

function controlFingerprint(element: Element): string {
	const input = element as HTMLInputElement;
	return [element.tagName, input.type ?? "", input.name ?? "", input.id ?? "", input.placeholder ?? ""].join(
		"\0",
	);
}

function resolveReplayTarget(element: Element): Element | null {
	if (element.isConnected) return element;
	const fingerprint = controlFingerprint(element);
	const matches = [...document.querySelectorAll(element.tagName)].filter(
		(el) => controlFingerprint(el) === fingerprint,
	);
	return matches.length === 1 ? matches[0] : (matches[0] ?? null);
}

/**
 * Set an input property so the next event registers as a change in React.
 *
 * React wraps `value`/`checked` with a tracker on the node instance and
 * dedupes events whose value matches the tracker — which is exactly the
 * pre-hydration state (the tracker initializes from the DOM). Move the
 * tracker to a different value through the instance setter, then write the
 * real value through the prototype setter the tracker can't observe.
 */
function setDesyncingReactTracker(
	element: Element,
	prop: "value" | "checked",
	next: string | boolean,
): boolean {
	const prototypeSetter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), prop)
		?.set;
	if (!prototypeSetter) return false;
	const instanceSetter = Object.getOwnPropertyDescriptor(element, prop)?.set;
	if (instanceSetter && instanceSetter !== prototypeSetter) {
		const sentinel = prop === "checked" ? !next : next === "" ? "\0" : "";
		instanceSetter.call(element, sentinel);
	}
	prototypeSetter.call(element, next);
	return true;
}
