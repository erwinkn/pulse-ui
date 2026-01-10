// Bun SSR server for Pulse applications
// Receives VDOM from Python and renders to HTML

import { type RenderConfig, renderVdom } from "pulse-ui-client";

const PORT = Number(process.env.PORT) || 3001;

interface RenderRequest {
	vdom: unknown;
	config?: RenderConfig;
}

const server = Bun.serve({
	port: PORT,
	async fetch(req) {
		const url = new URL(req.url);

		if (req.method === "GET" && url.pathname === "/health") {
			return new Response("OK", { status: 200 });
		}

		if (req.method === "POST" && url.pathname === "/render") {
			try {
				const body = (await req.json()) as RenderRequest;
				const html = renderVdom(body.vdom, body.config);
				return new Response(html, {
					status: 200,
					headers: { "Content-Type": "text/html; charset=utf-8" },
				});
			} catch (error) {
				const message = error instanceof Error ? error.message : "Internal server error";
				return new Response(JSON.stringify({ error: message }), {
					status: 500,
					headers: { "Content-Type": "application/json" },
				});
			}
		}

		return new Response("Not Found", { status: 404 });
	},
});

console.log(`Listening on http://localhost:${server.port}`);
