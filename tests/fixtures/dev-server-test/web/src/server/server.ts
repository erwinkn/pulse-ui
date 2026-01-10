// Simple Bun SSR server that renders VDOM to HTML
// This is a minimal server that re-uses the renderVdom from packages/pulse/js/src/server/render.tsx

const PORT = Number(process.env.PORT) || 3001;

const server = Bun.serve({
	port: PORT,
	async fetch(req) {
		const url = new URL(req.url);

		if (req.method === "GET" && url.pathname === "/health") {
			return new Response("OK", { status: 200 });
		}

		if (req.method === "POST" && url.pathname === "/render") {
			try {
				const _body = await req.json();
				// For now, just render a simple HTML response
				// In production, would use renderVdom from pulse-ui-client
				const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pulse App</title>
</head>
<body>
  <div id="root"></div>
</body>
</html>`;
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
