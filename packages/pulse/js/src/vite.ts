import { writeSync } from "node:fs";
import type { Plugin, ViteDevServer } from "vite";

const HMR_CLIENT_PORT_ENV = "PULSE_HMR_CLIENT_PORT";
const READY_FD_ENV = "PULSE_VITE_READY_FD";

function hmrClientPort(): number | undefined {
	const raw = process.env[HMR_CLIENT_PORT_ENV];
	if (raw === undefined || raw.trim() === "") return;
	const port = Number(raw);
	if (!Number.isInteger(port) || port <= 0) return;
	return port;
}

function readyFd(): number | undefined {
	const raw = process.env[READY_FD_ENV];
	if (raw === undefined || raw.trim() === "") return;
	const fd = Number(raw);
	if (!Number.isInteger(fd) || fd < 0) {
		throw new Error(
			`${READY_FD_ENV} must be a non-negative integer, got ${JSON.stringify(raw)}`,
		);
	}
	return fd;
}

export function pulseVitePlugin(): Plugin {
	const fd = readyFd();
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
			if (fd === undefined) return;
			writeSync(fd, "c");
			bindListening(server, () => writeSync(fd, "1"));
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
