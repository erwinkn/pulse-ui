import type { VDOM } from "../vdom";
import { type RenderConfig, renderVdom } from "./render";

const PORT = Number(process.env.PORT) || 3001;

interface RenderRequestBody {
	vdom: VDOM;
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
				const body = (await req.json()) as RenderRequestBody;
				const html = renderVdom(body.vdom, body.config ?? {});
				return new Response(html, {
					status: 200,
					headers: { "Content-Type": "text/html" },
				});
			} catch (error) {
				const message = error instanceof Error ? error.message : "Unknown error";
				return new Response(JSON.stringify({ error: message }), {
					status: 500,
					headers: { "Content-Type": "application/json" },
				});
			}
		}

		return new Response("Not Found", { status: 404 });
	},
});

console.log(`SSR server listening on http://localhost:${server.port}`);
