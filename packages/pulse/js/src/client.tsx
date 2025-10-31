import type { NavigateFunction } from "react-router";
import { io, type Socket } from "socket.io-client";
import type { ChannelBridge } from "./channel";
import { createChannelBridge, PulseChannelResetError } from "./channel";
import type { RouteInfo } from "./helpers";
import type {
	ClientApiResultMessage,
	ClientMessage,
	ServerApiCallMessage,
	ServerChannelMessage,
	ServerErrorInfo,
	ServerMessage,
} from "./messages";
import { extractEvent } from "./serialize/events";
import { deserialize, serialize } from "./serialize/serializer";
import type { VDOM, VDOMUpdate } from "./vdom";

export interface SocketIODirectives {
	headers?: Record<string, string>;
	auth?: Record<string, string>;
}
export interface Directives {
	headers?: Record<string, string>;
	socketio?: SocketIODirectives;
}
export interface MountedView {
	routeInfo: RouteInfo;
	onInit: (vdom: VDOM, callbacks: string[], renderProps: string[], cssRefs: string[]) => void;
	onUpdate: (ops: VDOMUpdate[]) => void;
}
export type ConnectionStatusListener = (connected: boolean) => void;
export type ServerErrorListener = (path: string, error: ServerErrorInfo | null) => void;

export interface PulseClient {
	// Connection management
	connect(): Promise<void>;
	disconnect(): void;
	isConnected(): boolean;
	onConnectionChange(listener: ConnectionStatusListener): () => void;
	// Messages
	navigate(path: string, routeInfo: RouteInfo): Promise<void>;
	leave(path: string): Promise<void>;
	invokeCallback(path: string, callback: string, args: any[]): Promise<void>;
	// VDOM subscription
	mountView(path: string, view: MountedView): () => void;
}

export class PulseSocketIOClient {
	#activeViews: Map<string, MountedView>;
	#socket: Socket | null = null;
	#messageQueue: ClientMessage[];
	#connectionListeners: Set<ConnectionStatusListener> = new Set();
	#serverErrors: Map<string, ServerErrorInfo> = new Map();
	#serverErrorListeners: Set<ServerErrorListener> = new Set();
	#channels: Map<string, { bridge: ChannelBridge; refCount: number }> = new Map();
	#url: string;
	#frameworkNavigate: NavigateFunction;
	#directives: Directives;

	constructor(url: string, directives: Directives, frameworkNavigate: NavigateFunction) {
		this.#url = url;
		this.#directives = directives;
		this.#frameworkNavigate = frameworkNavigate;
		this.#socket = null;
		this.#activeViews = new Map();
		this.#messageQueue = [];
		// Load directives from sessionStorage
		if (typeof window !== "undefined" && typeof sessionStorage !== "undefined") {
			const stored = sessionStorage.getItem("__PULSE_DIRECTIVES");
			if (stored) {
				try {
					this.#directives = JSON.parse(stored);
				} catch {
					// Ignore parse errors
				}
			}
		}
	}
	public isConnected(): boolean {
		return this.#socket?.connected ?? false;
	}

	public async connect(): Promise<void> {
		if (this.#socket) {
			return;
		}
		return new Promise((resolve, reject) => {
			const socket = io(this.#url, {
				transports: ["websocket", "webtransport"],
				auth: this.#directives.socketio?.auth,
				extraHeaders: this.#directives.socketio?.headers,
			});
			this.#socket = socket;

			socket.on("connect", () => {
				console.log("[SocketIOTransport] Connected:", this.#socket?.id);
				// Make sure to send a navigate payload for all the routes
				for (const [path, route] of this.#activeViews) {
					socket.emit(
						"message",
						serialize({
							type: "mount",
							path: path,
							routeInfo: route.routeInfo,
						}),
					);
				}

				for (const payload of this.#messageQueue) {
					// Already sent above
					if (payload.type === "mount" && this.#activeViews.has(payload.path)) {
						continue;
					}
					// We're remounting all the routes, so no need to navigate
					if (payload.type === "navigate") {
						continue;
					}
					socket.emit("message", serialize(payload));
				}
				this.#messageQueue = [];

				this.notifyConnectionListeners(true);
				resolve();
			});

			socket.on("connect_error", (err) => {
				console.error("[SocketIOTransport] Connection failed:", err);
				this.notifyConnectionListeners(false);
				reject(err);
			});

			socket.on("disconnect", () => {
				console.log("[SocketIOTransport] Disconnected");
				this.#handleTransportDisconnect();
				this.notifyConnectionListeners(false);
			});

			// Wrap in an arrow function to avoid losing the `this` reference
			socket.on("message", (data) =>
				this.#handleServerMessage(deserialize(data, { coerceNullsToUndefined: true })),
			);
		});
	}

	onConnectionChange(listener: ConnectionStatusListener): () => void {
		this.#connectionListeners.add(listener);
		listener(this.isConnected());
		return () => {
			this.#connectionListeners.delete(listener);
		};
	}

	private notifyConnectionListeners(connected: boolean): void {
		for (const listener of this.#connectionListeners) {
			listener(connected);
		}
	}

	public onServerError(listener: ServerErrorListener): () => void {
		this.#serverErrorListeners.add(listener);
		// Emit current errors to new listener
		for (const [path, err] of this.#serverErrors) listener(path, err);
		return () => {
			this.#serverErrorListeners.delete(listener);
		};
	}

	private notifyServerError(path: string, error: ServerErrorInfo | null) {
		for (const listener of this.#serverErrorListeners) listener(path, error);
	}

	public sendMessage(payload: ClientMessage) {
		if (this.isConnected()) {
			// console.log("[SocketIOTransport] Sending:", payload);
			this.#socket!.emit("message", serialize(payload as any));
		} else {
			// console.log("[SocketIOTransport] Queuing message:", payload);
			this.#messageQueue.push(payload);
		}
	}

	public mountView(path: string, view: MountedView) {
		if (this.#activeViews.has(path)) {
			throw new Error(`Path ${path} is already mounted`);
		}
		this.#activeViews.set(path, view);
		void this.sendMessage({
			type: "mount",
			path,
			routeInfo: view.routeInfo,
		});
	}

	public async navigate(path: string, routeInfo: RouteInfo) {
		await this.sendMessage({
			type: "navigate",
			path,
			routeInfo,
		});
	}

	public unmount(path: string) {
		void this.sendMessage({ type: "unmount", path });
		this.#activeViews.delete(path);
	}

	public disconnect() {
		this.#socket?.disconnect();
		this.#socket = null;
		this.#messageQueue = [];
		this.#connectionListeners.clear();
		this.#activeViews.clear();
		this.#serverErrors.clear();
		this.#serverErrorListeners.clear();
		for (const { bridge } of this.#channels.values()) {
			bridge.dispose(new PulseChannelResetError("Client disconnected"));
		}
		this.#channels.clear();
	}

	#handleServerMessage(message: ServerMessage) {
		// console.log("[PulseClient] Received message:", message);
		switch (message.type) {
			case "vdom_init": {
				const route = this.#activeViews.get(message.path);
				// Ignore messages for paths that are not mounted
				if (!route) return;
				if (route) {
					route.onInit(message.vdom, message.callbacks, message.render_props, message.css_refs);
				}
				// Clear any prior error for this path on successful init
				if (this.#serverErrors.has(message.path)) {
					this.#serverErrors.delete(message.path);
					this.notifyServerError(message.path, null);
				}
				break;
			}
			case "vdom_update": {
				const route = this.#activeViews.get(message.path);
				if (!route) return; // Not an active path; discard
				route.onUpdate(message.ops);
				// Clear any prior error for this path on successful update
				if (this.#serverErrors.has(message.path)) {
					this.#serverErrors.delete(message.path);
					this.notifyServerError(message.path, null);
				}
				break;
			}
			case "server_error": {
				if (!this.#activeViews.has(message.path)) return; // discard for inactive paths
				this.#serverErrors.set(message.path, message.error);
				this.notifyServerError(message.path, message.error);
				break;
			}
			case "api_call": {
				void this.#performApiCall(message);
				break;
			}
			case "navigate_to": {
				// `navigate_to` is navigational; allow regardless of activeViews membership
				const replace = !!message.replace;
				let dest = message.path || "";
				// Normalize protocol-relative URLs to absolute
				if (dest.startsWith("//")) dest = `${window.location.protocol}${dest}`;
				const hasScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(dest);
				if (hasScheme) {
					if (dest.startsWith("http://") || dest.startsWith("https://")) {
						try {
							const url = new URL(dest);
							if (url.origin === window.location.origin) {
								const internal = `${url.pathname}${url.search}${url.hash}`;
								this.#frameworkNavigate(internal, { replace });
							} else {
								if (replace) window.location.replace(dest);
								else window.location.assign(dest);
							}
						} catch {
							if (replace) window.location.replace(dest);
							else window.location.assign(dest);
						}
					} else {
						// mailto:, tel:, data:, etc.
						if (replace) window.location.replace(dest);
						else window.location.assign(dest);
					}
				} else {
					// Relative or root-relative path → SPA navigate
					this.#frameworkNavigate(dest, { replace });
				}
				break;
			}
			case "channel_message": {
				this.#routeChannelMessage(message);
				break;
			}
			default: {
				console.error("Unexpected message:", message);
			}
		}
	}

	async #performApiCall(msg: ServerApiCallMessage) {
		try {
			const res = await fetch(msg.url, {
				method: msg.method || "GET",
				headers: {
					...(msg.headers || {}),
					...(msg.body != null && !("content-type" in (msg.headers || {}))
						? { "content-type": "application/json" }
						: {}),
				},
				body:
					msg.body != null
						? typeof msg.body === "string"
							? msg.body
							: JSON.stringify(msg.body)
						: undefined,
				credentials: msg.credentials || "include",
			});
			const headersObj: Record<string, string> = {};
			res.headers.forEach((v, k) => {
				headersObj[k] = v;
			});
			let body: any = null;
			const ct = res.headers.get("content-type") || "";
			if (ct.includes("application/json")) {
				body = await res.json().catch(() => null);
			} else {
				body = await res.text().catch(() => null);
			}
			const reply: ClientApiResultMessage = {
				type: "api_result",
				id: msg.id,
				ok: res.ok,
				status: res.status,
				headers: headersObj,
				body,
			};
			this.sendMessage(reply);
		} catch (err) {
			const reply: ClientApiResultMessage = {
				type: "api_result",
				id: msg.id,
				ok: false,
				status: 0,
				headers: {},
				body: { error: String(err) },
			};
			this.sendMessage(reply);
		}
	}

	public invokeCallback(path: string, callback: string, args: any[]) {
		this.sendMessage({
			type: "callback",
			path,
			callback,
			args: args.map(extractEvent),
		});
	}

	public acquireChannel(id: string): ChannelBridge {
		const entry = this.#ensureChannelEntry(id);
		entry.refCount += 1;
		return entry.bridge;
	}

	public releaseChannel(id: string): void {
		const entry = this.#channels.get(id);
		if (!entry) {
			return;
		}
		entry.refCount = Math.max(0, entry.refCount - 1);
		if (entry.refCount === 0) {
			entry.bridge.dispose(new PulseChannelResetError("Channel released"));
			this.sendMessage({
				type: "channel_message",
				channel: id,
				event: "__close__",
				payload: { reason: "refcount_zero" },
			});
			this.#channels.delete(id);
		}
	}

	#ensureChannelEntry(id: string): {
		bridge: ChannelBridge;
		refCount: number;
	} {
		let entry = this.#channels.get(id);
		if (!entry) {
			entry = {
				bridge: createChannelBridge(this, id),
				refCount: 0,
			};
			this.#channels.set(id, entry);
		}
		return entry;
	}

	#routeChannelMessage(message: ServerChannelMessage): void {
		const entry = this.#ensureChannelEntry(message.channel);
		const closed = entry.bridge.handleServerMessage(message);
		if (closed && entry.refCount === 0) {
			this.#channels.delete(message.channel);
		}
	}

	#handleTransportDisconnect(): void {
		for (const entry of this.#channels.values()) {
			entry.bridge.handleDisconnect(new PulseChannelResetError("Connection lost"));
		}
	}
}
