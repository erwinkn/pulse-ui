import { afterEach, describe, expect, it, vi } from "bun:test";
import { pulseFetch } from "./http";

const originalFetch = globalThis.fetch;
const originalReload = Object.getOwnPropertyDescriptor(window.location, "reload");

afterEach(() => {
	globalThis.fetch = originalFetch;
	if (originalReload) {
		Object.defineProperty(window.location, "reload", originalReload);
	} else {
		Reflect.deleteProperty(window.location, "reload");
	}
	vi.restoreAllMocks();
});

describe("pulseFetch stale affinity recovery", () => {
	it("hard reloads in a browser and returns the marked response", async () => {
		const reload = vi.fn();
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const response = new Response("stale", {
			status: 409,
			headers: { "x-pulse-stale-affinity": "1" },
		});
		globalThis.fetch = vi.fn(async () => response) as any;

		const result = await pulseFetch("http://pulse.test/submit");

		expect(result).toBe(response);
		expect(reload).toHaveBeenCalledTimes(1);
	});

	it("returns an unrelated 409 without reloading", async () => {
		const reload = vi.fn();
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const response = new Response("conflict", { status: 409 });
		globalThis.fetch = vi.fn(async () => response) as any;

		const result = await pulseFetch("http://pulse.test/submit");

		expect(result).toBe(response);
		expect(await result.text()).toBe("conflict");
		expect(reload).not.toHaveBeenCalled();
	});

	it("returns a marked response outside the browser", async () => {
		const response = new Response("stale", {
			status: 409,
			headers: { "x-pulse-stale-affinity": "1" },
		});
		globalThis.fetch = vi.fn(async () => response) as any;
		const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
		Reflect.deleteProperty(globalThis, "window");

		try {
			const result = await pulseFetch("http://pulse.test/submit");
			expect(result).toBe(response);
		} finally {
			if (windowDescriptor) {
				Object.defineProperty(globalThis, "window", windowDescriptor);
			}
		}
	});
});
