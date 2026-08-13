import type { Plugin } from "vite";

const HMR_CLIENT_PORT_ENV = "PULSE_HMR_CLIENT_PORT";

function hmrClientPort(): number | undefined {
	const raw = process.env[HMR_CLIENT_PORT_ENV];
	if (raw === undefined || raw.trim() === "") return;
	const port = Number(raw);
	if (!Number.isInteger(port) || port <= 0) return;
	return port;
}

export function pulseVitePlugin(): Plugin {
	return {
		name: "pulse:hmr",
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
	};
}
