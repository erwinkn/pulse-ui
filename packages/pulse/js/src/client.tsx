import type { NavigateFunction } from "react-router";
import { io, type Socket } from "socket.io-client";
import { ChannelBridge, PulseChannelResetError } from "./channel";
import type { RouteInfo } from "./helpers";
import type {
	ClientApiResultMessage,
	ClientJsResultMessage,
	ClientMessage,
	ServerApiCallMessage,
	ServerChannelMessage,
	ServerError,
	ServerJsExecMessage,
	ServerMessage,
} from "./messages";
import type { PulsePrerenderView } from "./pulse";
import { extractEvent } from "./serialize/events";
import { deserialize, serialize } from "./serialize/serializer";
import type { VDOMUpdate } from "./vdom";

type RefPayload = {
	refId?: string;
	op?: string;
	payload?: any;
};

function isRefPayload(value: unknown): value is RefPayload {
	return typeof value === "object" && value !== null && "refId" in (value as any);
}

type RefOpResult = any;

class RefController {
	#client: PulseSocketIOClient;
	#channelId: string;
	#refId: string;
	#bridge: ChannelBridge;
	#cleanup: Array<() => void> = [];
	#node: any = null;
	#callback: (node: any) => void;

	constructor(client: PulseSocketIOClient, channelId: string, refId: string) {
		this.#client = client;
		this.#channelId = channelId;
		this.#refId = refId;
		const entry = this.#client._ensureChannelEntry(channelId);
		this.#bridge = entry.bridge;

		this.#cleanup.push(
			this.#bridge.on("ref:call", (payload) => {
				if (!this.#matches(payload)) return;
				this.#handleCall(payload);
			}),
			this.#bridge.on("ref:request", (payload) => {
				if (!this.#matches(payload)) return undefined;
				return this.#handleRequest(payload);
			}),
		);

		this.#callback = (node: any) => {
			this.#setNode(node ?? null);
		};
	}

	get callback() {
		return this.#callback;
	}

	get channelId() {
		return this.#channelId;
	}

	dispose() {
		for (const fn of this.#cleanup) fn();
		this.#cleanup = [];
		this.#node = null;
	}

	#matches(payload: unknown): payload is RefPayload {
		if (!isRefPayload(payload)) return false;
		const refId = payload.refId;
		return refId == null || String(refId) === this.#refId;
	}

	#setNode(node: any) {
		if (this.#node === node) return;
		this.#node = node;
		if (node) {
			this.#bridge.emit("ref:mounted", { refId: this.#refId });
		} else {
			this.#bridge.emit("ref:unmounted", { refId: this.#refId });
		}
	}

	#handleCall(payload: RefPayload) {
		const op = payload.op;
		if (!op) return;
		try {
			this.#perform(op, payload.payload, false);
		} catch (err) {
			console.error("[Pulse] Ref call failed:", err);
		}
	}

	#handleRequest(payload: RefPayload): RefOpResult {
		const op = payload.op;
		if (!op) {
			throw new Error("ref request missing op");
		}
		return this.#perform(op, payload.payload, true);
	}

	#perform(op: string, payload: any, needsResult: boolean): RefOpResult {
		const node = this.#node as any;
		if (!node) {
			const msg = "ref is not mounted";
			if (needsResult) throw new Error(msg);
			console.warn(`[Pulse] ${msg}`);
			return null;
		}

		switch (op) {
			case "focus":
				if (typeof node.focus === "function") node.focus();
				return null;
			case "blur":
				if (typeof node.blur === "function") node.blur();
				return null;
			case "click":
				if (typeof node.click === "function") node.click();
				return null;
			case "select":
				if (typeof node.select === "function") node.select();
				else throw new Error("select() not supported on this element");
				return null;
			case "scrollIntoView": {
				if (typeof node.scrollIntoView !== "function") {
					throw new Error("scrollIntoView() not supported on this element");
				}
				const options = payload ?? undefined;
				node.scrollIntoView(options);
				return null;
			}
			case "measure": {
				if (typeof node.getBoundingClientRect !== "function") {
					throw new Error("measure() not supported on this element");
				}
				const rect = node.getBoundingClientRect();
				return {
					x: rect.x,
					y: rect.y,
					width: rect.width,
					height: rect.height,
					top: rect.top,
					right: rect.right,
					bottom: rect.bottom,
					left: rect.left,
				};
			}
			case "getValue": {
				if ("value" in node) return (node as any).value;
				if ("textContent" in node) return (node as any).textContent;
				return null;
			}
			case "setValue": {
				const value = payload?.value;
				if ("value" in node) {
					(node as any).value = value;
					return (node as any).value;
				}
				if ("textContent" in node) {
					(node as any).textContent = value == null ? "" : String(value);
					return (node as any).textContent;
				}
				return null;
			}
			case "getText": {
				if ("textContent" in node) return (node as any).textContent;
				return null;
			}
			case "setText": {
				const text = payload?.text;
				if (typeof text !== "string") {
					throw new Error("setText() requires a string payload");
				}
				if ("textContent" in node) {
					(node as any).textContent = text;
					return (node as any).textContent;
				}
				return null;
			}
			default:
				throw new Error(`Unsupported ref op: ${op}`);
		}
	}
}

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
	onInit: (view: PulsePrerenderView) => void;
	onUpdate: (ops: VDOMUpdate[]) => void;
	onJsExec: (msg: ServerJsExecMessage) => void;
	onServerError: (error: ServerError) => void;
}
export type ConnectionStatus = "ok" | "connecting" | "reconnecting" | "error";
export type ConnectionStatusListener = (status: ConnectionStatus) => void;

export interface PulseClient {
	// Connection management
	connect(): Promise<void>;
	disconnect(): void;
	isConnected(): boolean;
	onConnectionChange(listener: ConnectionStatusListener): () => void;
	// Messages
	updateRoute(path: string, routeInfo: RouteInfo): void;
	invokeCallback(path: string, callback: string, args: any[]): void;
	// VDOM subscription
	attach(path: string, view: MountedView): void;
	detach(path: string): void;
}

export class PulseSocketIOClient {
	#activeViews: Map<string, MountedView>;
	#socket: Socket | null = null;
	#messageQueue: ClientMessage[];
	#connectionListeners: Set<ConnectionStatusListener> = new Set();
	#channels: Map<string, { bridge: ChannelBridge; refCount: number }> = new Map();
	#refControllers: Map<string, RefController> = new Map();
	#url: string;
	#frameworkNavigate: NavigateFunction;
	#directives: Directives;
	#connectionStatusConfig: {
		initialConnectingDelay: number;
		initialErrorDelay: number;
		reconnectErrorDelay: number;
	};
	#hasConnectedOnce: boolean = false;
	#connectingTimeout: ReturnType<typeof setTimeout> | null = null;
	#errorTimeout: ReturnType<typeof setTimeout> | null = null;
	#currentStatus: ConnectionStatus = "ok";

	constructor(
		url: string,
		directives: Directives,
		frameworkNavigate: NavigateFunction,
		connectionStatusConfig: {
			initialConnectingDelay: number;
			initialErrorDelay: number;
			reconnectErrorDelay: number;
		},
	) {
		this.#url = url;
		this.#directives = directives;
		this.#frameworkNavigate = frameworkNavigate;
		this.#socket = null;
		this.#activeViews = new Map();
		this.#messageQueue = [];
		this.#connectionStatusConfig = connectionStatusConfig;
	}
	public setDirectives(directives: Directives) {
		this.#directives = directives;
	}
	public isConnected(): boolean {
		return this.#socket?.connected ?? false;
	}

	#clearTimeouts(): void {
		if (this.#connectingTimeout) {
			clearTimeout(this.#connectingTimeout);
			this.#connectingTimeout = null;
		}
		if (this.#errorTimeout) {
			clearTimeout(this.#errorTimeout);
			this.#errorTimeout = null;
		}
	}

	#setStatus(status: ConnectionStatus): void {
		this.#clearTimeouts();
		this.#currentStatus = status;
		this.#notifyConnectionListeners(status);
	}

	#handleConnected(): void {
		this.#hasConnectedOnce = true;
		this.#setStatus("ok");
	}

	#setInitialConnectionStatus(): void {
		// Initial connection attempt - start with no message, then show connecting after delay
		this.#setStatus("ok");
		this.#connectingTimeout = setTimeout(() => {
			this.#setStatus("connecting");
			this.#errorTimeout = setTimeout(() => {
				this.#setStatus("error");
			}, this.#connectionStatusConfig.initialErrorDelay);
		}, this.#connectionStatusConfig.initialConnectingDelay);
	}

	#handleDisconnected(): void {
		// Reconnection after losing connection - show reconnecting immediately
		this.#setStatus("reconnecting");
		this.#errorTimeout = setTimeout(() => {
			this.#setStatus("error");
		}, this.#connectionStatusConfig.reconnectErrorDelay);
	}

	public async connect(): Promise<void> {
		if (this.#socket) {
			return;
		}
		// Start timing logic for connection attempt
		if (!this.#hasConnectedOnce) {
			this.#setInitialConnectionStatus();
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
				// Send attach for all active views on connect/reconnect
				for (const [path, route] of this.#activeViews) {
					socket.emit(
						"message",
						serialize({
							type: "attach",
							path: path,
							routeInfo: route.routeInfo,
						}),
					);
				}

				for (const payload of this.#messageQueue) {
					// Already sent above
					if (payload.type === "attach" && this.#activeViews.has(payload.path)) {
						continue;
					}
					// We're reattaching all the routes, so no need to send update
					if (payload.type === "update") {
						continue;
					}
					socket.emit("message", serialize(payload));
				}
				this.#messageQueue = [];

				this.#handleConnected();
				resolve();
			});

			socket.on("connect_error", (err) => {
				console.error("[SocketIOTransport] Connection failed:", err);
				this.#handleDisconnected();
				reject(err);
			});

			socket.on("disconnect", () => {
				console.log("[SocketIOTransport] Disconnected");
				this.#handleTransportDisconnect();
				this.#handleDisconnected();
			});

			// Wrap in an arrow function to avoid losing the `this` reference
			socket.on("message", (data) =>
				this.#handleServerMessage(deserialize(data, { coerceNullsToUndefined: true })),
			);
		});
	}

	onConnectionChange(listener: ConnectionStatusListener): () => void {
		this.#connectionListeners.add(listener);
		// Notify immediately with current status
		listener(this.#currentStatus);
		return () => {
			this.#connectionListeners.delete(listener);
		};
	}

	#notifyConnectionListeners(status: ConnectionStatus): void {
		for (const listener of this.#connectionListeners) {
			listener(status);
		}
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

	public attach(path: string, view: MountedView) {
		if (this.#activeViews.has(path)) {
			throw new Error(`Path ${path} is already attached`);
		}
		this.#activeViews.set(path, view);
		void this.sendMessage({
			type: "attach",
			path,
			routeInfo: view.routeInfo,
		});
	}

	public updateRoute(path: string, routeInfo: RouteInfo) {
		const view = this.#activeViews.get(path);
		if (view) {
			view.routeInfo = routeInfo;
			this.sendMessage({
				type: "update",
				path,
				routeInfo,
			});
		}
	}

	public detach(path: string) {
		void this.sendMessage({ type: "detach", path });
		this.#activeViews.delete(path);
	}

	public disconnect() {
		this.#clearTimeouts();
		this.#socket?.disconnect();
		this.#socket = null;
		this.#messageQueue = [];
		this.#connectionListeners.clear();
		this.#activeViews.clear();
		for (const { bridge } of this.#channels.values()) {
			bridge.dispose(new PulseChannelResetError("Client disconnected"));
		}
		this.#channels.clear();
		for (const controller of this.#refControllers.values()) {
			controller.dispose();
		}
		this.#refControllers.clear();
		this.#currentStatus = "ok";
		this.#hasConnectedOnce = false;
	}

	#handleServerMessage(message: ServerMessage) {
		// console.log("[PulseClient] Received message:", message);
		switch (message.type) {
			case "vdom_init": {
				const route = this.#activeViews.get(message.path);
				// Ignore messages for paths that are not mounted
				if (!route) return;
				route.onInit(message);
				break;
			}
			case "vdom_update": {
				const route = this.#activeViews.get(message.path);
				if (!route) return; // Not an active path; discard
				route.onUpdate(message.ops);
				break;
			}
			case "server_error": {
				const route = this.#activeViews.get(message.path);
				if (!route) return; // discard for inactive paths
				route.onServerError(message.error);
				break;
			}
			case "api_call": {
				void this.#performApiCall(message);
				break;
			}
			case "navigate_to": {
				const replace = !!message.replace;
				let dest = message.path || "";
				if (dest.startsWith("//")) dest = `${window.location.protocol}${dest}`;

				const hardNav = () =>
					replace ? window.location.replace(dest) : window.location.assign(dest);

				if (message.hard) {
					hardNav();
					break;
				}

				// No scheme = relative path → SPA
				if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(dest)) {
					this.#frameworkNavigate(dest, { replace });
					break;
				}

				// Same-origin http(s) → SPA
				if (/^https?:\/\//.test(dest)) {
					try {
						const url = new URL(dest);
						if (url.origin === window.location.origin) {
							this.#frameworkNavigate(`${url.pathname}${url.search}${url.hash}`, { replace });
							break;
						}
					} catch {}
				}

				// External URL or other scheme (mailto:, tel:, etc.)
				hardNav();
				break;
			}
			case "reload": {
				window.location.reload();
				break;
			}
			case "channel_message": {
				this.#routeChannelMessage(message);
				break;
			}
			case "js_exec": {
				this.#handleJsExec(message);
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

	#handleJsExec(message: ServerJsExecMessage) {
		const view = this.#activeViews.get(message.path);
		if (!view) {
			// View unmounted before the message arrived - send result back to unblock
			// the server-side future (which is likely already cancelled anyway).
			this.#sendJsResult(message.id, undefined, null);
			return;
		}
		view.onJsExec(message);
	}

	public sendJsResult(id: string, result: any, error: string | null) {
		this.#sendJsResult(id, result, error);
	}

	#sendJsResult(id: string, result: any, error: string | null) {
		const msg: ClientJsResultMessage = {
			type: "js_result",
			id,
			result,
			error,
		};
		this.sendMessage(msg);
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
				bridge: new ChannelBridge(this, id),
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
		if (message.event === "__close__" || closed) {
			this.#disposeRefControllersForChannel(message.channel);
		}
	}

	#handleTransportDisconnect(): void {
		for (const entry of this.#channels.values()) {
			entry.bridge.handleDisconnect(new PulseChannelResetError("Connection lost"));
		}
	}

	public getRefCallback(channelId: string, refId: string): (node: any) => void {
		const key = `${channelId}:${refId}`;
		let controller = this.#refControllers.get(key);
		if (!controller) {
			controller = new RefController(this, channelId, refId);
			this.#refControllers.set(key, controller);
		}
		return controller.callback;
	}

	#disposeRefControllersForChannel(channelId: string): void {
		for (const [key, controller] of this.#refControllers.entries()) {
			if (controller.channelId !== channelId) continue;
			controller.dispose();
			this.#refControllers.delete(key);
		}
	}

	_ensureChannelEntry(id: string): {
		bridge: ChannelBridge;
		refCount: number;
	} {
		return this.#ensureChannelEntry(id);
	}
}
