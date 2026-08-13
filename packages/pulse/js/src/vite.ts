import { fstatSync } from "node:fs";
import { request } from "node:http";
import type { Logger, Plugin } from "vite";

const URL_ENV = "PULSE_VITE_LIFECYCLE_URL";
const SECRET_ENV = "PULSE_VITE_LIFECYCLE_SECRET";
const INSTANCE_ENV = "PULSE_VITE_INSTANCE";
const HMR_CLIENT_PORT_ENV = "PULSE_HMR_CLIENT_PORT";
const STATE_KEY = Symbol.for("pulse.vite.lifecycle");
const NOTIFY_TIMEOUT_MS = 5000;

interface LifecycleConfig {
	url: string;
	secret: string;
	instance: string;
}

interface ServerRegistration {
	generation: number;
	listening: boolean;
	port?: number;
}

interface InstanceState {
	delivery: Promise<void>;
	latestGeneration: number;
	nextGeneration: number;
	registrations: WeakMap<object, ServerRegistration>;
	sequence: number;
}

interface LifecycleState {
	instances: Map<string, InstanceState>;
	watchingSupervisor?: boolean;
}

type LifecycleEvent = "closed" | "configured" | "listening";

function requiredEnv(name: string, value: string | undefined) {
	if (value === undefined || value.trim() === "") {
		throw new Error(`${name} must be set by the Pulse supervisor`);
	}
	return value;
}

function lifecycleConfig(): LifecycleConfig | undefined {
	const url = process.env[URL_ENV];
	const secret = process.env[SECRET_ENV];
	const instance = process.env[INSTANCE_ENV];
	if (url === undefined && secret === undefined && instance === undefined) return;

	const requiredUrl = requiredEnv(URL_ENV, url);
	const requiredSecret = requiredEnv(SECRET_ENV, secret);
	const requiredInstance = requiredEnv(INSTANCE_ENV, instance);

	let callback: URL;
	try {
		callback = new URL(requiredUrl);
	} catch {
		throw new Error(`${URL_ENV} must be a valid URL`);
	}
	if (
		callback.protocol !== "http:" ||
		(callback.hostname !== "127.0.0.1" && callback.hostname !== "[::1]") ||
		callback.username !== "" ||
		callback.password !== "" ||
		callback.hash !== ""
	) {
		throw new Error(
			`${URL_ENV} must be an unauthenticated HTTP URL on 127.0.0.1 or ::1`,
		);
	}

	return {
		url: requiredUrl,
		secret: requiredSecret,
		instance: requiredInstance,
	};
}

function lifecycleStateRoot() {
	const globalRecord = globalThis as unknown as Record<symbol, unknown>;
	return (globalRecord[STATE_KEY] ??= {
		instances: new Map(),
	}) as LifecycleState;
}

function stateFor(instance: string) {
	const lifecycleState = lifecycleStateRoot();
	let state = lifecycleState.instances.get(instance);
	if (!state) {
		state = {
			delivery: Promise.resolve(),
			latestGeneration: 0,
			nextGeneration: 0,
			registrations: new WeakMap(),
			sequence: 0,
		};
		lifecycleState.instances.set(instance, state);
	}
	return state;
}

function notify(
	lifecycle: LifecycleConfig,
	event: LifecycleEvent,
	sequence: number,
	port: number | undefined,
): Promise<void> {
	const body = JSON.stringify({
		event,
		instance: lifecycle.instance,
		sequence,
		port,
	});
	return new Promise((resolve, reject) => {
		const notification = request(
			lifecycle.url,
			{
				method: "POST",
				headers: {
					authorization: `Bearer ${lifecycle.secret}`,
					"content-length": Buffer.byteLength(body),
					"content-type": "application/json",
				},
			},
			(response) => {
				const status = response.statusCode ?? 0;
				response.resume();
				response.once("error", reject);
				response.once("end", () => {
					if (status >= 200 && status < 300) resolve();
					else reject(new Error(`supervisor returned HTTP ${status}`));
				});
			},
		);
		notification.setTimeout(NOTIFY_TIMEOUT_MS, () => {
			notification.destroy(new Error("supervisor timed out"));
		});
		notification.once("error", reject);
		notification.end(body);
	});
}

function enqueue(
	state: InstanceState,
	lifecycle: LifecycleConfig,
	event: LifecycleEvent,
	port: number | undefined,
	logger: Logger,
) {
	const sequence = ++state.sequence;
	state.delivery = state.delivery
		.then(() => notify(lifecycle, event, sequence, port))
		.catch((error: unknown) => {
			const message = error instanceof Error ? error.message : String(error);
			logger.error(`Pulse could not report Vite ${event}: ${message}`);
		});
}

function watchSupervisor() {
	const lifecycleState = lifecycleStateRoot();
	if (lifecycleState.watchingSupervisor) return;
	// The supervisor always feeds us stdin through a pipe. Anything else
	// (a TTY, /dev/null under a test runner) would hit EOF spuriously.
	// Windows anonymous pipes often report as sockets rather than FIFOs.
	try {
		const stat = fstatSync(0);
		if (!stat.isFIFO() && !stat.isSocket()) return;
	} catch {
		return;
	}
	lifecycleState.watchingSupervisor = true;
	// The supervisor holds our stdin pipe open for our whole lifetime; EOF
	// means it died without stopping us, so exit rather than run orphaned.
	const exit = () => process.exit(0);
	process.stdin.once("end", exit);
	process.stdin.once("close", exit);
	process.stdin.once("error", exit);
	process.stdin.resume();
	// Do not let the stdin watch alone keep the process alive.
	process.stdin.unref();
}

function hmrClientPort(): number | undefined {
	const raw = process.env[HMR_CLIENT_PORT_ENV];
	if (raw === undefined || raw.trim() === "") return;
	const port = Number(raw);
	if (!Number.isInteger(port) || port <= 0) return;
	return port;
}

export function pulseVitePlugin(): Plugin {
	const lifecycle = lifecycleConfig();
	const state = lifecycle ? stateFor(lifecycle.instance) : undefined;

	return {
		name: "pulse:lifecycle",
		apply: "serve",
		enforce: "post",
		config(userConfig) {
			if (!lifecycle) return;
			const clientPort = hmrClientPort();
			const existingHmr = userConfig.server?.hmr;
			return {
				server: {
					host: "127.0.0.1",
					port: 0,
					strictPort: false,
					...(clientPort === undefined
						? {}
						: {
								hmr: {
									...(typeof existingHmr === "object" && existingHmr
										? existingHmr
										: {}),
									clientPort,
								},
							}),
				},
			};
		},
		configureServer(server) {
			if (!lifecycle || !state) return;
			watchSupervisor();
			const httpServer = server.httpServer;
			if (!httpServer) {
				throw new Error("Pulse lifecycle requires Vite to own an HTTP server");
			}

			enqueue(state, lifecycle, "configured", undefined, server.config.logger);
			const existing = state.registrations.get(httpServer);
			if (existing) {
				existing.generation = state.latestGeneration;
				return;
			}

			const generation = ++state.nextGeneration;
			state.latestGeneration = generation;
			const registration: ServerRegistration = {
				generation,
				listening: false,
			};
			state.registrations.set(httpServer, registration);

			const reportListening = () => {
				if (
					registration.listening ||
					registration.generation !== state.latestGeneration
				) {
					return;
				}
				const address = httpServer.address();
				if (!address || typeof address === "string") {
					server.config.logger.error(
						"Pulse could not report Vite listening: server has no TCP port",
					);
					return;
				}
				registration.listening = true;
				registration.port = address.port;
				enqueue(
					state,
					lifecycle,
					"listening",
					address.port,
					server.config.logger,
				);
			};

			httpServer.once("close", () => {
				if (
					!registration.listening ||
					registration.port === undefined ||
					registration.generation !== state.latestGeneration
				) {
					return;
				}
				enqueue(
					state,
					lifecycle,
					"closed",
					registration.port,
					server.config.logger,
				);
			});
			if (httpServer.listening) queueMicrotask(reportListening);
			else httpServer.once("listening", reportListening);
		},
	};
}
