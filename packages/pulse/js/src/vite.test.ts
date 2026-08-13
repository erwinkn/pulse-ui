import { afterEach, describe, expect, it } from "bun:test";
import {
	createServer as createHttpServer,
	type IncomingMessage,
	type Server,
	type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";
import type { ViteDevServer } from "vite";
import { pulseVitePlugin } from "./vite";

const ENV_NAMES = ["PULSE_HMR_CLIENT_PORT", "PULSE_VITE_READY_URL"] as const;
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

async function waitFor(check: () => boolean) {
	for (let attempt = 0; attempt < 100; attempt++) {
		if (check()) return;
		await Bun.sleep(10);
	}
	throw new Error("Timed out waiting for condition");
}

function viteServer(httpServer: Server, error = (_message: string) => {}) {
	return {
		config: { logger: { error } },
		httpServer,
	} as unknown as ViteDevServer;
}

async function readyCallback() {
	const paths: string[] = [];
	const server = createHttpServer(
		(request: IncomingMessage, response: ServerResponse) => {
			paths.push(request.url ?? "");
			response.writeHead(204).end();
		},
	);
	await listen(server);
	const port = (server.address() as AddressInfo).port;
	const token = "ready-token";
	process.env.PULSE_VITE_READY_URL = `http://127.0.0.1:${port}/${token}`;
	return { server, paths, token };
}

describe("pulseVitePlugin", () => {
	it("is a no-op without supervisor env", () => {
		for (const name of ENV_NAMES) delete process.env[name];
		const plugin = pulseVitePlugin();
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

	it("rejects non-loopback ready URLs", () => {
		process.env.PULSE_VITE_READY_URL = "http://192.168.1.5:9/x";
		expect(() => pulseVitePlugin()).toThrow("HTTP loopback URL");
	});

	it("sets HMR clientPort from the supervisor", () => {
		process.env.PULSE_HMR_CLIENT_PORT = "8000";
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
		process.env.PULSE_HMR_CLIENT_PORT = "5173";
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

	it("posts configured then listening to the supervisor", async () => {
		const callback = await readyCallback();
		const viteHttp = createHttpServer();
		try {
			hook(pulseVitePlugin().configureServer).call(
				{} as never,
				viteServer(viteHttp),
			);
			await waitFor(() => callback.paths.includes(`/${callback.token}/configured`));
			await listen(viteHttp);
			await waitFor(() => callback.paths.includes(`/${callback.token}/listening`));
			expect(callback.paths).toEqual([
				`/${callback.token}/configured`,
				`/${callback.token}/listening`,
			]);
		} finally {
			if (viteHttp.listening) await close(viteHttp);
			await close(callback.server);
		}
	});
});
