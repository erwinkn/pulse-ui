const PORT = Number(process.env.PORT) || 3001;

const server = Bun.serve({
	port: PORT,
	async fetch(req) {
		const url = new URL(req.url);

		if (req.method === "GET" && url.pathname === "/health") {
			return new Response("OK", { status: 200 });
		}

		if (req.method === "POST" && url.pathname === "/render") {
			return new Response("<div>placeholder</div>", {
				status: 200,
				headers: { "Content-Type": "text/html" },
			});
		}

		return new Response("Not Found", { status: 404 });
	},
});

console.log(`SSR server listening on http://localhost:${server.port}`);
