import { existsSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const port = Number(process.env.PULSE_SSR_PORT ?? 3001);
const isProd = process.env.PULSE_ENV === "prod";
const prodEntryPath = join(import.meta.dir, "..", "dist", "server", "entry-server.js");
const codegenPaths = [
	join(import.meta.dir, "..", "app", "pulse", "routes.ts"),
	join(import.meta.dir, "..", "app", "pulse", "_layout.tsx"),
];
const renderTimeoutMs = 5_000;
const renderPollMs = 100;

type RenderFn = (url: string, prerender: unknown) => Promise<string>;
let renderPromise: Promise<RenderFn> | null = null;

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
	if (!renderPromise) {
		renderPromise = (async () => {
			if (isProd && existsSync(prodEntryPath)) {
				const mod = await import(pathToFileURL(prodEntryPath).href);
				return mod.render as RenderFn;
			}
			await waitForCodegen();
			const mod = await import("../src/entry-server");
			return mod.render as RenderFn;
		})();
	}
	return renderPromise;
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
				const message = error instanceof Error ? error.message : "SSR error";
				return new Response(message, { status: 503 });
			}
		}
		return new Response("Not found", { status: 404 });
	},
});

console.log(`SSR server running on http://localhost:${server.port}`);
