import { afterEach, describe, expect, it, vi } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import {
	createServer as createHttpServer,
	type IncomingMessage,
	type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import {
	createServer as createViteServer,
	type Plugin,
	type ResolvedConfig,
	type ViteDevServer,
} from "vite";
import { pulseVitePlugin } from "./vite";

const SECRET = "pulse-test-secret";
const originalSecret = process.env.PULSE_VITE_CONTROL_SECRET;
const originalGeneratedDir = process.env.PULSE_VITE_GENERATED_DIR;
const originalStagingDir = process.env.PULSE_VITE_STAGING_DIR;

afterEach(() => {
	if (originalSecret === undefined) delete process.env.PULSE_VITE_CONTROL_SECRET;
	else process.env.PULSE_VITE_CONTROL_SECRET = originalSecret;
	if (originalGeneratedDir === undefined) delete process.env.PULSE_VITE_GENERATED_DIR;
	else process.env.PULSE_VITE_GENERATED_DIR = originalGeneratedDir;
	if (originalStagingDir === undefined) delete process.env.PULSE_VITE_STAGING_DIR;
	else process.env.PULSE_VITE_STAGING_DIR = originalStagingDir;
});

function createPlugin(generatedDir?: string) {
	process.env.PULSE_VITE_CONTROL_SECRET = SECRET;
	const plugin = pulseVitePlugin({ generatedDir });
	delete process.env.PULSE_VITE_CONTROL_SECRET;
	return plugin;
}

function hook<T extends (...args: never[]) => unknown>(
	value: T | { handler: T } | undefined,
) {
	if (!value) throw new Error("Expected plugin hook");
	return typeof value === "function" ? value : value.handler;
}

type Middleware = (
	request: IncomingMessage,
	response: ServerResponse,
	next: () => void,
) => void | Promise<void>;

async function startPlugin(options?: {
	generatedDir?: string;
	invalidate?: ReturnType<typeof vi.fn>;
}) {
	const invalidate = options?.invalidate ?? vi.fn();
	const send = vi.fn();
	const logError = vi.fn();
	const plugin = createPlugin(options?.generatedDir);
	let middleware: Middleware | undefined;
	const moduleNode = {} as never;
	const server = {
		config: { logger: { error: logError } },
		environments: {
			client: {
				moduleGraph: {
					getModulesByFile: vi.fn(() => new Set([moduleNode])),
					invalidateModule: invalidate,
				},
			},
			ssr: {
				moduleGraph: {
					getModulesByFile: vi.fn(() => new Set([moduleNode])),
					invalidateModule: invalidate,
				},
			},
		},
		middlewares: {
			use: vi.fn((handler: Middleware) => {
				middleware = handler;
			}),
		},
		ws: { send },
	} as unknown as ViteDevServer;

	await hook(plugin.configResolved).call(
		{} as never,
		{ root: "/project/web" } as ResolvedConfig,
	);
	await hook(plugin.configureServer).call({} as never, server);
	if (!middleware) throw new Error("Expected Pulse middleware");

	const httpServer = createHttpServer((request, response) => {
		void middleware?.(request, response, () => {
			response.writeHead(404).end();
		});
	});
	await new Promise<void>((resolve, reject) => {
		httpServer.once("error", reject);
		httpServer.listen(0, "127.0.0.1", resolve);
	});
	const port = (httpServer.address() as AddressInfo).port;

	return {
		plugin,
		invalidate,
		send,
		logError,
		url: `http://127.0.0.1:${port}`,
		async close() {
			await new Promise<void>((resolve, reject) => {
				httpServer.close((error) => (error ? reject(error) : resolve()));
			});
		},
	};
}

function controlFetch(url: string, path: string, init: RequestInit = {}) {
	return Bun.fetch(`${url}${path}`, {
		...init,
		headers: {
			authorization: `Bearer ${SECRET}`,
			...init.headers,
		},
	});
}

describe("pulseVitePlugin", () => {
	it("stays inactive outside a Pulse-supervised Vite process", async () => {
		delete process.env.PULSE_VITE_CONTROL_SECRET;
		const plugin = pulseVitePlugin();
		const use = vi.fn();
		const result = await hook(plugin.configureServer).call(
			{} as never,
			{ middlewares: { use } } as unknown as ViteDevServer,
		);
		expect(result).toBeUndefined();
		expect(use).not.toHaveBeenCalled();
	});

	it("rejects an empty control secret", () => {
		process.env.PULSE_VITE_CONTROL_SECRET = "";
		expect(() => pulseVitePlugin()).toThrow(
			"PULSE_VITE_CONTROL_SECRET must not be empty",
		);
	});

	it("reports readiness, requires the random secret, and passes other URLs through", async () => {
		const control = await startPlugin();
		try {
			const unauthorized = await Bun.fetch(`${control.url}/__pulse/health`);
			expect(unauthorized.status).toBe(401);

			const response = await controlFetch(control.url, "/__pulse/health");
			expect(response.status).toBe(200);
			expect(await response.json()).toEqual({
				status: "ready",
				generation: 0,
			});

			const unrelated = await Bun.fetch(`${control.url}/somewhere-else`);
			expect(unrelated.status).toBe(404);
		} finally {
			await control.close();
		}
	});

	it("invalidates all module graphs and commits each generation idempotently", async () => {
		const control = await startPlugin();
		try {
			await hook(control.plugin.hotUpdate).call(
				{} as never,
				{ file: "/project/web/app/pulse/routes.ts" } as never,
			);
			const first = await controlFetch(control.url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({
					generation: 1,
					files: ["/project/web/app/pulse/routes.ts"],
				}),
			});
			expect(first.status).toBe(200);
			expect(await first.json()).toEqual({
				status: "committed",
				generation: 1,
			});
			expect(control.invalidate).toHaveBeenCalledTimes(2);
			expect(control.send).toHaveBeenCalledTimes(1);
			expect(control.send).toHaveBeenLastCalledWith({ type: "full-reload" });

			const repeated = await controlFetch(control.url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 1 }),
			});
			expect(repeated.status).toBe(200);
			expect(await repeated.json()).toEqual({
				status: "committed",
				generation: 1,
			});
			expect(control.invalidate).toHaveBeenCalledTimes(2);
			expect(control.send).toHaveBeenCalledTimes(1);

			const newest = await controlFetch(control.url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 3 }),
			});
			expect(newest.status).toBe(200);
			expect(control.invalidate).toHaveBeenCalledTimes(2);
			expect(control.send).toHaveBeenCalledTimes(2);

			const stale = await controlFetch(control.url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 2 }),
			});
			expect(stale.status).toBe(409);
			expect(await stale.json()).toEqual({ status: "stale", generation: 3 });
		} finally {
			await control.close();
		}
	});

	it("rejects malformed, invalid, and oversized commits", async () => {
		const control = await startPlugin();
		try {
			for (const body of [
				"not json",
				JSON.stringify({ generation: 0 }),
				JSON.stringify({ generation: "1" }),
				JSON.stringify({ generation: 1, files: "route.ts" }),
				JSON.stringify({ generation: 1, files: ["/project/secret.ts"] }),
				JSON.stringify({ generation: 1, padding: "x".repeat(70_000) }),
			]) {
				const response = await controlFetch(control.url, "/__pulse/commit", {
					method: "POST",
					body,
				});
				expect(response.status).toBe(400);
			}
			expect(control.invalidate).not.toHaveBeenCalled();
			expect(control.send).not.toHaveBeenCalled();
		} finally {
			await control.close();
		}
	});

	it("does not advance the generation when invalidation fails", async () => {
		const invalidate = vi.fn().mockImplementationOnce(() => {
			throw new Error("invalidation failed");
		});
		const control = await startPlugin({ invalidate });
		try {
			await hook(control.plugin.hotUpdate).call(
				{} as never,
				{ file: "/project/web/app/pulse/routes.ts" } as never,
			);
			const failed = await controlFetch(control.url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 2 }),
			});
			expect(failed.status).toBe(500);
			expect(control.send).not.toHaveBeenCalled();
			expect(control.logError).toHaveBeenCalledTimes(1);

			const recovered = await controlFetch(control.url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 2 }),
			});
			expect(recovered.status).toBe(200);
			expect(control.send).toHaveBeenCalledTimes(1);
		} finally {
			await control.close();
		}
	});

	it("suppresses generated file HMR only while coordinated", async () => {
		const control = await startPlugin({ generatedDir: "app/generated" });
		try {
			const hotUpdate = hook(control.plugin.hotUpdate);
			expect(
				typeof control.plugin.hotUpdate === "object" &&
					control.plugin.hotUpdate.order,
			).toBe("pre");
			expect(
				await hotUpdate.call(
					{} as never,
					{ file: "/project/web/app/generated/routes.ts" } as never,
				),
			).toEqual([]);
			expect(
				await hotUpdate.call(
					{} as never,
					{
						file: "/project/web/app/.generated.pulse-reload/run-1/routes.ts",
					} as never,
				),
			).toEqual([]);
			expect(
				await hotUpdate.call(
					{} as never,
					{ file: "/project/web/app/generated-other/routes.ts" } as never,
				),
			).toBeUndefined();
			expect(
				await hotUpdate.call(
					{} as never,
					{ file: "/project/web/app/routes/home.tsx" } as never,
				),
			).toBeUndefined();
		} finally {
			await control.close();
		}
	});

	it("uses the supervisor-provided generated directory", async () => {
		process.env.PULSE_VITE_GENERATED_DIR = "app/custom-pulse";
		process.env.PULSE_VITE_STAGING_DIR = ".pulse/reload/custom-pulse";
		const control = await startPlugin();
		try {
			const hotUpdate = hook(control.plugin.hotUpdate);
			expect(
				await hotUpdate.call(
					{} as never,
					{ file: "/project/web/app/custom-pulse/routes.ts" } as never,
				),
			).toEqual([]);
			expect(
				await hotUpdate.call(
					{} as never,
					{ file: "/project/web/.pulse/reload/custom-pulse/routes.ts" } as never,
				),
			).toEqual([]);
		} finally {
			await control.close();
		}
	});

	it("keeps the middleware available when Vite reloads its config", async () => {
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
		process.env.PULSE_VITE_CONTROL_SECRET = SECRET;
		let server: ViteDevServer | undefined;
		try {
			server = await createViteServer({ configFile, logLevel: "silent", root });
			await server.listen();
			const address = server.httpServer?.address() as AddressInfo;
			const url = `http://127.0.0.1:${address.port}`;

			const committed = await controlFetch(url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 7 }),
			});
			expect(committed.status).toBe(200);

			await server.restart();

			const health = await controlFetch(url, "/__pulse/health");
			expect(health.status).toBe(200);
			expect(await health.json()).toEqual({
				status: "ready",
				generation: 0,
			});

			const next = await controlFetch(url, "/__pulse/commit", {
				method: "POST",
				body: JSON.stringify({ generation: 8 }),
			});
			expect(next.status).toBe(200);
			expect(await next.json()).toEqual({
				status: "committed",
				generation: 8,
			});
		} finally {
			await server?.close();
			await rm(root, { force: true, recursive: true });
		}
	});
});
