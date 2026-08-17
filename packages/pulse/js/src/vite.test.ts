import { afterEach, describe, expect, it } from "bun:test";
import { closeSync, openSync, readFileSync, unlinkSync } from "node:fs";
import { createServer as createHttpServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ViteDevServer } from "vite";
import { pulse } from "./vite";

const ENV_NAMES = ["PULSE_HMR_CLIENT_PORT", "PULSE_VITE_READY_FD"] as const;
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
		try {
			expect(
				hook(plugin.config).call({} as never, {} as never, {} as never),
			).toBeUndefined();
			expect(
				hook(plugin.configureServer).call({} as never, viteServer(server)),
			).toBeUndefined();
			expect(server.listenerCount("listening")).toBe(0);
		} finally {
			server.close();
		}
	});

	it("rejects a non-integer ready fd", () => {
		process.env.PULSE_VITE_READY_FD = "nope";
		expect(() => pulse()).toThrow("non-negative integer");
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

	it("writes configured then listening to the ready fd", async () => {
		const path = join(tmpdir(), `pulse-vite-ready-${process.pid}-${Date.now()}`);
		const fd = openSync(path, "w");
		process.env.PULSE_VITE_READY_FD = String(fd);
		const viteHttp = createHttpServer();
		try {
			hook(pulse().configureServer).call({} as never, viteServer(viteHttp));
			await listen(viteHttp);
			closeSync(fd);
			expect(readFileSync(path, "utf8")).toBe("c1");
		} finally {
			if (viteHttp.listening) await close(viteHttp);
			try {
				unlinkSync(path);
			} catch {}
		}
	});

	it("does not throw when the supervisor has closed the ready fd", () => {
		const path = join(tmpdir(), `pulse-vite-closed-${process.pid}-${Date.now()}`);
		const fd = openSync(path, "w");
		process.env.PULSE_VITE_READY_FD = String(fd);
		closeSync(fd);
		const viteHttp = createHttpServer();
		try {
			expect(() =>
				hook(pulse().configureServer).call({} as never, viteServer(viteHttp)),
			).not.toThrow();
		} finally {
			viteHttp.close();
			try {
				unlinkSync(path);
			} catch {}
		}
	});

	it("rejects middleware mode", () => {
		const path = join(tmpdir(), `pulse-vite-mw-${process.pid}-${Date.now()}`);
		const fd = openSync(path, "w");
		process.env.PULSE_VITE_READY_FD = String(fd);
		try {
			expect(() =>
				hook(pulse().configureServer).call({} as never, viteServer(null)),
			).toThrow("HTTP server");
		} finally {
			closeSync(fd);
			try {
				unlinkSync(path);
			} catch {}
		}
	});
});
