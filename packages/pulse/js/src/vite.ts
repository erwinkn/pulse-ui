import { request as httpRequest } from "node:http";
import type { Plugin, ViteDevServer } from "vite";

const HMR_CLIENT_PORT_ENV = "PULSE_HMR_CLIENT_PORT";
const READY_URL_ENV = "PULSE_VITE_READY_URL";

function hmrClientPort(): number | undefined {
	const raw = process.env[HMR_CLIENT_PORT_ENV];
	if (raw === undefined || raw.trim() === "") return;
	const port = Number(raw);
	if (!Number.isInteger(port) || port <= 0) return;
	return port;
}

function readyUrl(): string | undefined {
	const raw = process.env[READY_URL_ENV];
	if (raw === undefined || raw.trim() === "") return;
	let url: URL;
	try {
		url = new URL(raw);
	} catch {
		throw new Error(`${READY_URL_ENV} must be an HTTP loopback URL`);
	}
	if (url.protocol !== "http:" || url.username || url.password) {
		throw new Error(`${READY_URL_ENV} must be an HTTP loopback URL`);
	}
	if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
		throw new Error(`${READY_URL_ENV} must be an HTTP loopback URL`);
	}
	return raw.replace(/\/$/, "");
}

function ping(base: string, event: "configured" | "listening", error: (msg: string) => void) {
	const url = new URL(`${base}/${event}`);
	const req = httpRequest(
		{
			hostname: url.hostname,
			port: url.port,
			path: `${url.pathname}${url.search}`,
			method: "POST",
		},
		(response) => {
			response.resume();
			if (response.statusCode !== undefined && response.statusCode >= 400) {
				error(
					`Pulse could not report Vite ${event}: supervisor returned HTTP ${response.statusCode}`,
				);
			}
		},
	);
	req.on("error", (cause) => {
		error(`Pulse could not report Vite ${event}: ${cause.message}`);
	});
	req.end();
}

export function pulseVitePlugin(): Plugin {
	const ready = readyUrl();
	return {
		name: "pulse",
		apply: "serve",
		enforce: "post",
		config(userConfig) {
			const clientPort = hmrClientPort();
			if (clientPort === undefined) return;
			const existingHmr = userConfig.server?.hmr;
			return {
				server: {
					hmr: {
						...(typeof existingHmr === "object" && existingHmr
							? existingHmr
							: {}),
						clientPort,
					},
				},
			};
		},
		configureServer(server) {
			if (ready === undefined) return;
			const logError = (message: string) => {
				server.config.logger.error(message);
			};
			ping(ready, "configured", logError);
			bindListening(server, () => ping(ready, "listening", logError));
		},
	};
}

function bindListening(server: ViteDevServer, onListening: () => void) {
	const httpServer = server.httpServer;
	if (!httpServer) return;
	if (httpServer.listening) {
		onListening();
		return;
	}
	httpServer.once("listening", onListening);
}
