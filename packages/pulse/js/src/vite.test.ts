import { afterEach, describe, expect, it } from "bun:test";
import { createServer as createHttpServer, type Server } from "node:http";
import type { ViteDevServer } from "vite";
import { pulse } from "./vite";

const ENV_NAMES = ["PULSE_HMR_CLIENT_PORT", "PULSE_SUPERVISED"] as const;
const originalEnv = Object.fromEntries(
	ENV_NAMES.map((name) => [name, process.env[name]]),
) as Record<(typeof ENV_NAMES)[number], string | undefined>;

afterEach(() => {
	for (const name of ENV_NAMES) {
		const value = originalEnv[name];
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
});

function hook<T extends (...args: never[]) => unknown>(
	value: T | { handler: T } | undefined,
) {
	if (!value) throw new Error("Expected plugin hook");
	return typeof value === "function" ? value : value.handler;
}

async function listen(server: Server) {
	await new Promise<void>((resolve, reject) => {
		server.once("error", reject);
		server.listen(0, "127.0.0.1", resolve);
	});
}

async function close(server: Server) {
	await new Promise<void>((resolve, reject) => {
		server.close((error) => (error ? reject(error) : resolve()));
	});
}

function viteServer(httpServer: Server | null) {
	return {
		config: { logger: { error: (_message: string) => {} } },
		httpServer,
	} as unknown as ViteDevServer;
}

describe("pulse", () => {
	it("is a no-op without supervisor env", () => {
		for (const name of ENV_NAMES) delete process.env[name];
		const plugin = pulse();
		const server = createHttpServer();
		const listenerCount = server.listenerCount("listening");
		try {
			expect(
				hook(plugin.config).call({} as never, {} as never, {} as never),
			).toBeUndefined();
			expect(
				hook(plugin.configureServer).call({} as never, viteServer(server)),
			).toBeUndefined();
			expect(server.listenerCount("listening")).toBe(listenerCount);
		} finally {
			server.close();
		}
	});

	it("sets HMR clientPort from the supervisor", () => {
		process.env.PULSE_HMR_CLIENT_PORT = "8000";
		const plugin = pulse();
		expect(
			hook(plugin.config).call({} as never, {} as never, {} as never),
		).toEqual({
			server: {
				hmr: { clientPort: 8000 },
			},
		});
	});

	it("merges clientPort into the user's Vite hmr config", () => {
		process.env.PULSE_HMR_CLIENT_PORT = "5173";
		const plugin = pulse();
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

	it("respects hmr: false", () => {
		process.env.PULSE_HMR_CLIENT_PORT = "5173";
		const plugin = pulse();
		expect(
			hook(plugin.config).call(
				{} as never,
				{ server: { hmr: false } } as never,
				{} as never,
			),
		).toBeUndefined();
	});

	it("writes configured then listening to stdout", async () => {
		process.env.PULSE_SUPERVISED = "1";
		let output = "";
		const write = process.stdout.write;
		process.stdout.write = ((chunk: string | Uint8Array) => {
			output += chunk.toString();
			return true;
		}) as typeof process.stdout.write;
		const viteHttp = createHttpServer();
		try {
			hook(pulse().configureServer).call({} as never, viteServer(viteHttp));
			await listen(viteHttp);
			expect(output).toBe(
				"\n\x00pulse:vite-configured\n\n\x00pulse:vite-listening\n",
			);
		} finally {
			process.stdout.write = write;
			if (viteHttp.listening) await close(viteHttp);
		}
	});

	it("does not throw when stdout is unavailable", () => {
		process.env.PULSE_SUPERVISED = "1";
		const write = process.stdout.write;
		process.stdout.write = (() => {
			throw new Error("closed");
		}) as typeof process.stdout.write;
		const viteHttp = createHttpServer();
		try {
			expect(() =>
				hook(pulse().configureServer).call({} as never, viteServer(viteHttp)),
			).not.toThrow();
		} finally {
			process.stdout.write = write;
			viteHttp.close();
		}
	});

	it("rejects middleware mode", () => {
		process.env.PULSE_SUPERVISED = "1";
		try {
			expect(() =>
				hook(pulse().configureServer).call({} as never, viteServer(null)),
			).toThrow("HTTP server");
		} finally {
		}
	});
});
