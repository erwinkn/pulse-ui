import { afterEach, describe, expect, it, vi } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import {
	createServer as createHttpServer,
	type IncomingMessage,
	type Server,
	type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
	createServer as createViteServer,
	type ViteDevServer,
} from "vite";
import { pulseVitePlugin } from "./vite";

const ENV_NAMES = [
	"PULSE_VITE_LIFECYCLE_URL",
	"PULSE_VITE_LIFECYCLE_SECRET",
	"PULSE_VITE_INSTANCE",
] as const;
const originalEnv = Object.fromEntries(
	ENV_NAMES.map((name) => [name, process.env[name]]),
) as Record<(typeof ENV_NAMES)[number], string | undefined>;
let nextInstance = 0;

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

function setLifecycleEnv(url: string) {
	const instance = `vite-${++nextInstance}`;
	process.env.PULSE_VITE_LIFECYCLE_URL = url;
	process.env.PULSE_VITE_LIFECYCLE_SECRET = "test secret";
	process.env.PULSE_VITE_INSTANCE = instance;
	return instance;
}

function viteServer(httpServer: Server, error = vi.fn()) {
	return {
		config: { logger: { error } },
		httpServer,
	} as unknown as ViteDevServer;
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

interface LifecycleBody {
	event: "closed" | "configured" | "listening";
	instance: string;
	port?: number;
	sequence: number;
}

interface ReceivedRequest {
	headers: IncomingMessage["headers"];
	body: LifecycleBody;
}

async function callbackServer(
	respond: (
		request: IncomingMessage,
		response: ServerResponse,
		body: LifecycleBody,
	) => void | Promise<void> = (_request, response) => {
		response.writeHead(204).end();
	},
) {
	const requests: ReceivedRequest[] = [];
	const server = createHttpServer(async (request, response) => {
		const chunks: Buffer[] = [];
		for await (const chunk of request) chunks.push(Buffer.from(chunk));
		const body = JSON.parse(
			Buffer.concat(chunks).toString("utf8"),
		) as LifecycleBody;
		requests.push({ headers: request.headers, body });
		await respond(request, response, body);
	});
	await listen(server);
	const port = (server.address() as AddressInfo).port;
	return { server, requests, url: `http://127.0.0.1:${port}/vite` };
}

describe("pulseVitePlugin", () => {
	it("is inactive outside a Pulse-supervised process", () => {
		for (const name of ENV_NAMES) delete process.env[name];
		const plugin = pulseVitePlugin();
		const server = createHttpServer();
		try {
			expect(
				hook(plugin.configureServer).call(
					{} as never,
					viteServer(server),
				),
			).toBeUndefined();
			expect(server.listenerCount("listening")).toBe(0);
		} finally {
			server.close();
		}
	});

	it("rejects incomplete and empty supervisor configuration", () => {
		for (const name of ENV_NAMES) delete process.env[name];
		process.env.PULSE_VITE_LIFECYCLE_URL = "http://127.0.0.1:1234/";
		expect(() => pulseVitePlugin()).toThrow(
			"PULSE_VITE_LIFECYCLE_SECRET must be set",
		);

		process.env.PULSE_VITE_LIFECYCLE_SECRET = " ";
		process.env.PULSE_VITE_INSTANCE = "vite-1";
		expect(() => pulseVitePlugin()).toThrow(
			"PULSE_VITE_LIFECYCLE_SECRET must be set",
		);
	});

	it("accepts only direct loopback HTTP callback URLs", () => {
		// Built via the URL API so no credential-shaped literal lands in source.
		const withUserinfo = new URL("http://127.0.0.1:1234/");
		withUserinfo.username = "user";
		withUserinfo.password = "placeholder";
		for (const url of [
			"not-a-url",
			"https://127.0.0.1:1234/",
			"http://localhost:1234/",
			"http://192.168.1.5:1234/",
			withUserinfo.href,
		]) {
			setLifecycleEnv(url);
			expect(() => pulseVitePlugin()).toThrow(
				"PULSE_VITE_LIFECYCLE_URL must be",
			);
		}
	});

	it("posts authenticated, ordered listening and closed events", async () => {
		const callback = await callbackServer();
		const viteHttpServer = createHttpServer();
		const instance = setLifecycleEnv(callback.url);
		try {
			const plugin = pulseVitePlugin();
			const configureServer = hook(plugin.configureServer);
			const server = viteServer(viteHttpServer);
			configureServer.call({} as never, server);
			configureServer.call({} as never, server);
			await listen(viteHttpServer);
			const port = (viteHttpServer.address() as AddressInfo).port;
			await waitFor(() => callback.requests.length === 3);
			expect(callback.requests[0]?.headers.authorization).toBe(
				"Bearer test secret",
			);
			expect(callback.requests[0]?.headers["content-type"]).toBe(
				"application/json",
			);
			// Each configureServer call reports "configured" before any listening.
			expect(callback.requests[0]?.body).toEqual({
				event: "configured",
				instance,
				sequence: 1,
			});
			expect(callback.requests[1]?.body).toEqual({
				event: "configured",
				instance,
				sequence: 2,
			});
			expect(callback.requests[2]?.body).toEqual({
				event: "listening",
				instance,
				sequence: 3,
				port,
			});

			await close(viteHttpServer);
			await waitFor(() => callback.requests.length === 4);
			expect(callback.requests[3]?.body).toEqual({
				event: "closed",
				instance,
				sequence: 4,
				port,
			});
		} finally {
			if (viteHttpServer.listening) await close(viteHttpServer);
			await close(callback.server);
		}
	});

	it("serializes lifecycle delivery", async () => {
		let releaseListening: (() => void) | undefined;
		const listeningResponse = new Promise<void>((resolve) => {
			releaseListening = resolve;
		});
		const callback = await callbackServer(async (_request, response, body) => {
			if (body.event === "listening") await listeningResponse;
			response.writeHead(204).end();
		});
		const viteHttpServer = createHttpServer();
		try {
			setLifecycleEnv(callback.url);
			const plugin = pulseVitePlugin();
			hook(plugin.configureServer).call(
				{} as never,
				viteServer(viteHttpServer),
			);
			await listen(viteHttpServer);
			// "configured" resolves immediately; "listening" is received but held
			// open, so "closed" must wait behind it in the delivery chain.
			await waitFor(() => callback.requests.length === 2);
			await close(viteHttpServer);
			await Bun.sleep(25);
			expect(callback.requests).toHaveLength(2);

			releaseListening?.();
			await waitFor(() => callback.requests.length === 3);
			expect(callback.requests.map(({ body }) => body.event)).toEqual([
				"configured",
				"listening",
				"closed",
			]);
			expect(callback.requests.map(({ body }) => body.sequence)).toEqual([
				1, 2, 3,
			]);
		} finally {
			releaseListening?.();
			if (viteHttpServer.listening) await close(viteHttpServer);
			await close(callback.server);
		}
	});

	it("logs failed callbacks without crashing Vite", async () => {
		const callback = await callbackServer((_request, response) => {
			response.writeHead(503).end();
		});
		const viteHttpServer = createHttpServer();
		const logError = vi.fn();
		try {
			setLifecycleEnv(callback.url);
			const plugin = pulseVitePlugin();
			hook(plugin.configureServer).call(
				{} as never,
				viteServer(viteHttpServer, logError),
			);
			await listen(viteHttpServer);
			await waitFor(() => logError.mock.calls.length === 2);
			expect(logError).toHaveBeenNthCalledWith(
				1,
				"Pulse could not report Vite configured: supervisor returned HTTP 503",
			);
			expect(logError).toHaveBeenNthCalledWith(
				2,
				"Pulse could not report Vite listening: supervisor returned HTTP 503",
			);
			expect(viteHttpServer.listening).toBe(true);

			await close(viteHttpServer);
			await waitFor(() => logError.mock.calls.length === 3);
			expect(logError).toHaveBeenNthCalledWith(
				3,
				"Pulse could not report Vite closed: supervisor returned HTTP 503",
			);
		} finally {
			if (viteHttpServer.listening) await close(viteHttpServer);
			await close(callback.server);
		}
	});

	it("suppresses stale closed events during a real Vite config restart", async () => {
		const callback = await callbackServer();
		const root = await mkdtemp(join(tmpdir(), "pulse-vite-restart-"));
		const configFile = join(root, "vite.config.ts");
		const pluginPath = fileURLToPath(new URL("./vite.ts", import.meta.url));
		await writeFile(
			configFile,
			`import { pulseVitePlugin } from ${JSON.stringify(pluginPath)};

export default {
	appType: "custom",
	plugins: [pulseVitePlugin()],
	server: { host: "127.0.0.1", port: 0, strictPort: true },
};
`,
		);
		const instance = setLifecycleEnv(callback.url);
		let server: ViteDevServer | undefined;
		try {
			server = await createViteServer({ configFile, logLevel: "silent", root });
			await server.listen();
			await waitFor(() => callback.requests.length === 2);

			await server.restart();
			await waitFor(() => callback.requests.length === 4);
			expect(callback.requests.map(({ body }) => body.event)).toEqual([
				"configured",
				"listening",
				"configured",
				"listening",
			]);
			expect(callback.requests.map(({ body }) => body.sequence)).toEqual([
				1, 2, 3, 4,
			]);
			expect(callback.requests.every(({ body }) => body.instance === instance)).toBe(
				true,
			);

			await server.close();
			server = undefined;
			await waitFor(() => callback.requests.length === 5);
			expect(callback.requests[4]?.body.event).toBe("closed");
			expect(callback.requests[4]?.body.sequence).toBe(5);
		} finally {
			await server?.close();
			await close(callback.server);
			await rm(root, { force: true, recursive: true });
		}
	});

	it("suppresses closed events from a reused plugin with a new HTTP server", async () => {
		const callback = await callbackServer();
		const first = createHttpServer();
		const second = createHttpServer();
		const instance = setLifecycleEnv(callback.url);
		try {
			const plugin = pulseVitePlugin();
			const configureServer = hook(plugin.configureServer);
			configureServer.call({} as never, viteServer(first));
			await listen(first);
			await waitFor(() => callback.requests.length === 2);

			configureServer.call({} as never, viteServer(second));
			await listen(second);
			const secondPort = (second.address() as AddressInfo).port;
			await waitFor(() => callback.requests.length === 4);

			await close(first);
			await Bun.sleep(25);
			expect(callback.requests.map(({ body }) => body.event)).toEqual([
				"configured",
				"listening",
				"configured",
				"listening",
			]);

			await close(second);
			await waitFor(() => callback.requests.length === 5);
			expect(callback.requests[4]?.body).toEqual({
				event: "closed",
				instance,
				sequence: 5,
				port: secondPort,
			});
		} finally {
			if (first.listening) await close(first);
			if (second.listening) await close(second);
			await close(callback.server);
		}
	});

	it("forces loopback ephemeral bind and HMR client port when supervised", () => {
		process.env.PULSE_HMR_CLIENT_PORT = "8000";
		setLifecycleEnv("http://127.0.0.1:1234/vite");
		const plugin = pulseVitePlugin();
		expect(hook(plugin.config)({} as never, {} as never)).toEqual({
			server: {
				host: "127.0.0.1",
				port: 0,
				strictPort: false,
				hmr: { clientPort: 8000 },
			},
		});
	});
});
