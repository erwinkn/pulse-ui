import type React from "react";
import { renderToString } from "react-dom/server";
import { ssrRouteLoaders } from "../src/routes";
import { type ComponentRegistry, renderVdom, type VdomNode } from "../src/vdom-renderer";

/** Hardcoded VDOM for each route (mirrors app.tsx) */
const routeVdom: Record<string, VdomNode> = {
	"/": {
		type: "HomeWidget",
		props: {},
		children: [],
	},
	"/dashboard": {
		type: "DashboardChart",
		props: {},
		children: [],
	},
	"/settings": {
		type: "SettingsForm",
		props: {},
		children: [],
	},
};

interface RenderRequest {
	pathname: string;
}

interface RenderResponse {
	html: string;
	vdom: VdomNode;
}

const server = Bun.serve({
	port: 3001,
	async fetch(req) {
		const url = new URL(req.url);

		if (req.method === "POST" && url.pathname === "/render") {
			const body = (await req.json()) as RenderRequest;
			const { pathname } = body;

			// Check if route exists
			const loader = ssrRouteLoaders[pathname];
			if (!loader) {
				return new Response(JSON.stringify({ error: "Route not found" }), {
					status: 404,
					headers: { "Content-Type": "application/json" },
				});
			}

			// Load route registry synchronously
			const routeModule = loader();
			const registry: ComponentRegistry = routeModule.registry;

			// Get VDOM for this route
			const vdom = routeVdom[pathname] ?? null;
			if (!vdom) {
				return new Response(JSON.stringify({ error: "No VDOM for route" }), {
					status: 404,
					headers: { "Content-Type": "application/json" },
				});
			}

			// Render VDOM to HTML string
			const reactNode = renderVdom(vdom, registry);
			const html = renderToString(reactNode as React.ReactElement);

			const response: RenderResponse = { html, vdom };
			return new Response(JSON.stringify(response), {
				headers: { "Content-Type": "application/json" },
			});
		}

		return new Response("Not found", { status: 404 });
	},
});

console.log(`SSR server running on http://localhost:${server.port}`);
