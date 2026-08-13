import { afterEach, describe, expect, it } from "bun:test";
import { pulseVitePlugin } from "./vite";

const ENV_NAME = "PULSE_HMR_CLIENT_PORT";
const original = process.env[ENV_NAME];

afterEach(() => {
	if (original === undefined) delete process.env[ENV_NAME];
	else process.env[ENV_NAME] = original;
});

function hook<T extends (...args: never[]) => unknown>(
	value: T | { handler: T } | undefined,
) {
	if (!value) throw new Error("Expected plugin hook");
	return typeof value === "function" ? value : value.handler;
}

describe("pulseVitePlugin", () => {
	it("is a no-op without PULSE_HMR_CLIENT_PORT", () => {
		delete process.env[ENV_NAME];
		const plugin = pulseVitePlugin();
		expect(
			hook(plugin.config).call({} as never, {} as never, {} as never),
		).toBeUndefined();
	});

	it("ignores empty and invalid HMR client ports", () => {
		for (const raw of ["", " ", "nope", "0", "-1", "1.5"]) {
			process.env[ENV_NAME] = raw;
			const plugin = pulseVitePlugin();
			expect(
				hook(plugin.config).call({} as never, {} as never, {} as never),
			).toBeUndefined();
		}
	});

	it("sets HMR clientPort from the supervisor", () => {
		process.env[ENV_NAME] = "8000";
		const plugin = pulseVitePlugin();
		expect(
			hook(plugin.config).call({} as never, {} as never, {} as never),
		).toEqual({
			server: {
				hmr: { clientPort: 8000 },
			},
		});
	});

	it("merges clientPort into the user's Vite hmr config", () => {
		process.env[ENV_NAME] = "5173";
		const plugin = pulseVitePlugin();
		expect(
			hook(plugin.config).call(
				{} as never,
				{
					server: { hmr: { protocol: "wss", host: "dev.example" } },
				} as never,
				{} as never,
			),
		).toEqual({
			server: {
				hmr: {
					protocol: "wss",
					host: "dev.example",
					clientPort: 5173,
				},
			},
		});
	});
});
