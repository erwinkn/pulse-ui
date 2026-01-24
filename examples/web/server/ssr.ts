import { existsSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import type { ViteDevServer } from "vite";

const port = Number(process.env.PULSE_SSR_PORT ?? 3001);
const isProd = process.env.PULSE_ENV === "prod";
const webRoot = join(import.meta.dir, "..");
const prodEntryPath = join(import.meta.dir, "..", "dist", "server", "entry-server.js");
const codegenPaths = [
	join(import.meta.dir, "..", "app", "pulse", "routes.ts"),
	join(import.meta.dir, "..", "app", "pulse", "_layout.tsx"),
];
const renderTimeoutMs = 5_000;
const renderPollMs = 100;

type RenderFn = (url: string, prerender: unknown) => Promise<string>;
let prodRenderPromise: Promise<RenderFn> | null = null;
let viteServer: ViteDevServer | null = null;

async function waitForCodegen() {
	const start = Date.now();
	while (Date.now() - start < renderTimeoutMs) {
		if (codegenPaths.every((path) => existsSync(path))) {
			return;
		}
		await new Promise((resolve) => setTimeout(resolve, renderPollMs));
	}
	throw new Error("Pulse codegen not ready");
}

async function getRender() {
	if (isProd && existsSync(prodEntryPath)) {
		if (!prodRenderPromise) {
			prodRenderPromise = (async () => {
				const mod = await import(pathToFileURL(prodEntryPath).href);
				return mod.render as RenderFn;
			})();
		}
		return prodRenderPromise;
	}

	await waitForCodegen();
	if (!viteServer) {
		const { createServer } = await import("vite");
		viteServer = await createServer({
			root: webRoot,
			server: { middlewareMode: true, hmr: false, ws: false },
			appType: "custom",
		});
	}
	const mod = await viteServer.ssrLoadModule("/src/entry-server.tsx");
	return mod.render as RenderFn;
}

type RenderRequest = {
	url: string;
	prerender: unknown;
};

const server = Bun.serve({
	port,
	async fetch(req) {
		const { pathname } = new URL(req.url);
		if (req.method === "POST" && pathname === "/render") {
			const body = (await req.json()) as RenderRequest;
			try {
				const render = await getRender();
				const html = await render(body.url, body.prerender);
				return new Response(html, { headers: { "Content-Type": "text/html" } });
			} catch (error) {
				if (!isProd && viteServer && error instanceof Error) {
					viteServer.ssrFixStacktrace(error);
				}
				const message = error instanceof Error ? error.message : "SSR error";
				return new Response(message, { status: 503 });
			}
		}
		return new Response("Not found", { status: 404 });
	},
});

console.log(`SSR server running on http://localhost:${server.port}`);
