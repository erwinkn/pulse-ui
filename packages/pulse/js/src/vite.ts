import type { Plugin, ViteDevServer } from "vite";

const HMR_CLIENT_PORT_ENV = "PULSE_HMR_CLIENT_PORT";
const SUPERVISED_ENV = "PULSE_SUPERVISED";
const PROTOCOL_PREFIX = "\x00pulse:";
const VITE_CONFIGURED = "vite-configured";
const VITE_LISTENING = "vite-listening";

function hmrClientPort(): number | undefined {
	const raw = process.env[HMR_CLIENT_PORT_ENV];
	if (raw === undefined || raw.trim() === "") return;
	const port = Number(raw);
	if (!Number.isInteger(port) || port <= 0) return;
	return port;
}

export function pulse(): Plugin {
	const supervised = process.env[SUPERVISED_ENV] === "1";
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
			if (!supervised) return;
			const httpServer = server.httpServer;
			if (!httpServer) {
				throw new Error(
					"Pulse Vite plugin requires an HTTP server. Middleware mode is not supported.",
				);
			}
			notify(VITE_CONFIGURED);
			bindListening(httpServer, () => notify(VITE_LISTENING));
		},
	};
}

function notify(message: string) {
	try {
		process.stdout.write(`\n${PROTOCOL_PREFIX}${message}\n`);
	} catch {
		// Readiness reporting must never prevent Vite from starting.
	}
}

function bindListening(
	httpServer: NonNullable<ViteDevServer["httpServer"]>,
	onListening: () => void,
) {
	if (httpServer.listening) {
		onListening();
		return;
	}
	httpServer.once("listening", onListening);
}
