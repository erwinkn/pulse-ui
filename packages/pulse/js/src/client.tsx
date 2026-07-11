import type { NavigateFunction } from "react-router";
import { io, type Socket } from "socket.io-client";
import { ChannelBridge, PulseChannelResetError } from "./channel";
import type { RouteInfo } from "./helpers";
import type {
	ClientApiResultMessage,
	ClientCallbackMessage,
	ClientJsResultMessage,
	ClientMessage,
	ServerApiCallMessage,
	ServerChannelMessage,
	ServerError,
	ServerJsExecMessage,
	ServerMessage,
	ViewSnapshot,
} from "./messages";
import { extractEvent } from "./serialize/events";
import { deserialize, serialize } from "./serialize/serializer";
import type { VDOMUpdate } from "./vdom";

function documentIsHidden(): boolean {
	return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function browserIsOnline(): boolean {
	return typeof navigator === "undefined" || navigator.onLine !== false;
}

const CLIENT_QUEUE_LIMIT = 10_000;
const CLIENT_QUEUE_OVERFLOW_MESSAGE =
	"Pulse client queue exceeded 10,000 messages; reloading to restore synchronization";

export interface SocketIODirectives {
	headers?: Record<string, string>;
	auth?: Record<string, string>;
	query?: Record<string, string>;
}
export interface Directives {
	headers?: Record<string, string>;
	query?: Record<string, string>;
	socketio?: SocketIODirectives;
}
export interface MountedView {
	routeInfo: RouteInfo;
	onInit: (view: ViewSnapshot) => void;
	onUpdate: (ops: VDOMUpdate[], viewId: string, revision: number) => void;
	onJsExec: (msg: ServerJsExecMessage) => void;
	onServerError: (error: ServerError) => void;
}
export type ConnectionStatus = "ok" | "connecting" | "reconnecting" | "error";
export type ConnectionStatusListener = (status: ConnectionStatus) => void;

export interface PulseClient {
	// Connection management
	connect(): Promise<void>;
	suspend(): void;
	resume(): Promise<void>;
	disconnect(): void;
	isConnected(): boolean;
	onConnectionChange(listener: ConnectionStatusListener): () => void;
	// Messages
	updateRoute(path: string, routeInfo: RouteInfo): void;
	invokeCallback(path: string, viewId: string, revision: number, callback: string, args: any[]): void;
	// VDOM subscription
	attach(path: string, snapshot: ViewSnapshot, instanceId: string, view: MountedView): void;
	installSnapshot(path: string, snapshot: ViewSnapshot): void;
	detach(path: string, instanceId: string): void;
}

interface ActiveView extends MountedView {
	viewId: string;
	revision: number;
	instanceId: string;
}

export class PulseSocketIOClient {
	#activeViews: Map<string, ActiveView>;
	#activeAttachIds: Map<string, string>;
	#ackedAttachIds: Map<string, string>;
	#pendingCallbacks: Map<string, ClientCallbackMessage[]>;
	#pendingCallbackCount = 0;
	#socket: Socket | null = null;
	#messageQueue: ClientMessage[];
	#queueOverflowed = false;
	#connectionListeners: Set<ConnectionStatusListener> = new Set();
	#channels: Map<string, { bridge: ChannelBridge; refCount: number }> = new Map();
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
	#nextAttachId = 0;
	#suspended = false;
	#reloadOnReconnectTimeout = false;

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
		this.#activeAttachIds = new Map();
		this.#ackedAttachIds = new Map();
		this.#pendingCallbacks = new Map();
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
		this.#reloadOnReconnectTimeout = false;
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
		if (this.#currentStatus === "reconnecting" && this.#errorTimeout) return;
		if (this.#currentStatus === "error") return;
		// Reconnection after losing connection - show reconnecting immediately
		this.#setStatus("reconnecting");
		this.#errorTimeout = setTimeout(() => {
			this.#handleReconnectTimedOut();
		}, this.#connectionStatusConfig.reconnectErrorDelay);
	}

	#handleConnectionError(): void {
		if (this.#hasConnectedOnce) {
			this.#handleDisconnected();
		}
	}

	#handleReconnectTimedOut(): void {
		this.#setStatus("error");
		if (
			this.#hasConnectedOnce &&
			!this.#suspended &&
			this.#reloadOnReconnectTimeout &&
			!documentIsHidden() &&
			browserIsOnline() &&
			typeof window !== "undefined"
		) {
			window.location.reload();
		}
	}

	public async connect(): Promise<void> {
		if (this.#socket) {
			return;
		}
		this.#suspended = false;
		// Start timing logic for connection attempt
		if (!this.#hasConnectedOnce) {
			this.#setInitialConnectionStatus();
		} else {
			this.#handleDisconnected();
		}
		return new Promise((resolve, reject) => {
			const socket = io(this.#url, {
				transports: ["websocket", "webtransport"],
				auth: this.#directives.socketio?.auth,
				query: this.#directives.socketio?.query,
			});
			this.#socket = socket;

			socket.on("connect", () => {
				if (this.#socket !== socket) return;
				console.log("[SocketIOTransport] Connected:", this.#socket?.id);
				// Send attach for all active views on connect/reconnect
				for (const path of this.#activeViews.keys()) {
					this.#sendAttach(path, socket);
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
				if (this.#socket !== socket) return;
				console.error("[SocketIOTransport] Connection failed:", err);
				this.#handleConnectionError();
				reject(err);
			});

			socket.on("disconnect", () => {
				if (this.#socket !== socket) return;
				console.log("[SocketIOTransport] Disconnected");
				this.#handleTransportDisconnect();
				this.#handleDisconnected();
				if (!socket.active && !this.#suspended) socket.connect();
			});

			// Wrap in an arrow function to avoid losing the `this` reference
			socket.on("message", (data) => {
				if (this.#socket !== socket) return;
				this.#handleServerMessage(deserialize(data, { coerceNullsToUndefined: true }));
			});
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
		if (this.#queueOverflowed) {
			throw new Error(CLIENT_QUEUE_OVERFLOW_MESSAGE);
		}
		if (this.isConnected()) {
			// console.log("[SocketIOTransport] Sending:", payload);
			this.#socket!.emit("message", serialize(payload as any));
		} else {
			// console.log("[SocketIOTransport] Queuing message:", payload);
			this.#reserveQueueSlot();
			this.#messageQueue.push(payload);
		}
	}

	public attach(path: string, snapshot: ViewSnapshot, instanceId: string, view: MountedView) {
		if (this.#activeViews.has(path)) {
			throw new Error(`Path ${path} is already attached`);
		}
		this.#activeViews.set(path, {
			...view,
			viewId: snapshot.viewId,
			revision: snapshot.revision,
			instanceId,
		});
		this.#sendAttach(path);
	}

	public installSnapshot(path: string, snapshot: ViewSnapshot): void {
		const view = this.#activeViews.get(path);
		if (!view) return;
		if (snapshot.viewId === view.viewId && snapshot.revision <= view.revision) return;
		this.#installSnapshot(path, view, snapshot);
		this.#sendAttach(path);
	}

	public updateRoute(path: string, routeInfo: RouteInfo) {
		const view = this.#activeViews.get(path);
		if (view) {
			view.routeInfo = routeInfo;
			this.sendMessage({
				type: "update",
				path,
				viewId: view.viewId,
				revision: view.revision,
				routeInfo,
			});
		}
	}

	public detach(path: string, instanceId: string) {
		const view = this.#activeViews.get(path);
		if (!view || view.instanceId !== instanceId) return;
		this.#activeViews.delete(path);
		this.#activeAttachIds.delete(path);
		this.#ackedAttachIds.delete(path);
		this.#deletePendingCallbacks(path);
		void this.sendMessage({ type: "detach", path, viewId: view.viewId, instanceId });
	}

	public suspend() {
		if (this.#suspended) return;
		this.#suspended = true;
		this.#reloadOnReconnectTimeout = false;
		this.#clearTimeouts();
		this.#closeSocket();
		this.#setStatus("ok");
	}

	public resume(): Promise<void> {
		if (!this.#suspended && this.#socket) {
			return Promise.resolve();
		}
		const wasSuspended = this.#suspended;
		this.#suspended = false;
		this.#reloadOnReconnectTimeout = wasSuspended;
		return this.connect();
	}

	public disconnect() {
		this.#suspended = false;
		this.#reloadOnReconnectTimeout = false;
		this.#clearTimeouts();
		this.#closeSocket();
		this.#messageQueue = [];
		this.#queueOverflowed = false;
		this.#connectionListeners.clear();
		this.#activeViews.clear();
		this.#activeAttachIds.clear();
		this.#ackedAttachIds.clear();
		this.#pendingCallbacks.clear();
		this.#pendingCallbackCount = 0;
		for (const { bridge } of this.#channels.values()) {
			bridge.dispose(new PulseChannelResetError("Client disconnected"));
		}
		this.#channels.clear();
		this.#currentStatus = "ok";
		this.#hasConnectedOnce = false;
	}

	#closeSocket(): void {
		const socket = this.#socket;
		if (!socket) return;
		this.#socket = null;
		this.#handleTransportDisconnect();
		socket.disconnect();
	}

	#handleServerMessage(message: ServerMessage) {
		// console.log("[PulseClient] Received message:", message);
		switch (message.type) {
			case "vdom_update": {
				const view = this.#activeViews.get(message.path);
				if (!view) return;
				if (message.viewId !== view.viewId || message.revision <= view.revision) return;
				if (
					message.baseRevision !== view.revision ||
					message.revision <= message.baseRevision
				) {
					this.#requestResync(message.path);
					return;
				}
				view.revision = message.revision;
				view.onUpdate(message.ops, message.viewId, message.revision);
				break;
			}
			case "server_error": {
				const route = this.#activeViews.get(message.path);
				if (!route) return; // discard for inactive paths
				if (message.viewId && message.viewId !== route.viewId) return;
				route.onServerError(message.error);
				break;
			}
			case "api_call": {
				void this.#performApiCall(message);
				break;
			}
			case "navigate_to": {
				if (message.origin) {
					let originActive = false;
					for (const view of this.#activeViews.values()) {
						if (
							view.viewId === message.origin.viewId &&
							view.routeInfo.pathname === message.origin.pathname
						) {
							originActive = true;
							break;
						}
					}
					if (!originActive) break;
				}
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
			case "attach_ack": {
				this.#handleAttachAck(message);
				break;
			}
			case "resync_view": {
				const view = this.#activeViews.get(message.path);
				if (view?.viewId === message.viewId) this.#requestResync(message.path);
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

	public invokeCallback(
		path: string,
		viewId: string,
		revision: number,
		callback: string,
		args: any[],
	) {
		const view = this.#activeViews.get(path);
		if (!view || view.viewId !== viewId) return;
		const message: ClientCallbackMessage = {
			type: "callback",
			path,
			viewId,
			revision,
			callback,
			args,
		};
		if (this.#isAttachAcked(path)) {
			this.sendMessage(message);
			return;
		}
		this.#queueCallback(message);
	}

	#handleJsExec(message: ServerJsExecMessage) {
		const view = this.#activeViews.get(message.path);
		if (!view || view.viewId !== message.viewId) {
			// View unmounted before the message arrived - send result back to unblock
			// the server-side future (which is likely already cancelled anyway).
			this.#sendJsResult(
				message.viewId,
				message.id,
				undefined,
				"View is no longer active",
			);
			return;
		}
		view.onJsExec(message);
	}

	public sendJsResult(viewId: string, id: string, result: any, error: string | null) {
		this.#sendJsResult(viewId, id, result, error);
	}

	#sendJsResult(viewId: string, id: string, result: any, error: string | null) {
		const msg: ClientJsResultMessage = {
			type: "js_result",
			viewId,
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
	}

	#handleTransportDisconnect(): void {
		this.#ackedAttachIds.clear();
		for (const entry of this.#channels.values()) {
			entry.bridge.handleDisconnect(new PulseChannelResetError("Connection lost"));
		}
	}

	#sendAttach(path: string, socket?: Socket): void {
		const view = this.#activeViews.get(path);
		if (!view) return;
		const attachId = `${path}:${++this.#nextAttachId}`;
		this.#activeAttachIds.set(path, attachId);
		this.#ackedAttachIds.delete(path);
		const message = {
			type: "attach" as const,
			path,
			routeInfo: view.routeInfo,
			attachId,
			viewId: view.viewId,
			revision: view.revision,
			instanceId: view.instanceId,
		};
		if (socket) {
			socket.emit("message", serialize(message));
			return;
		}
		this.sendMessage(message);
	}

	#isAttachAcked(path: string): boolean {
		const attachId = this.#activeAttachIds.get(path);
		return attachId !== undefined && this.#ackedAttachIds.get(path) === attachId;
	}

	#handleAttachAck(message: Extract<ServerMessage, { type: "attach_ack" }>): void {
		const { path, attachId } = message;
		if (this.#activeAttachIds.get(path) !== attachId) return;
		const view = this.#activeViews.get(path);
		if (!view) return;
		if (message.snapshot) {
			if (
				message.snapshot.viewId !== message.viewId ||
				message.snapshot.revision !== message.revision
			) {
				throw new Error("Attach snapshot metadata does not match its acknowledgement");
			}
			this.#installSnapshot(path, view, message.snapshot);
		}
		if (view.viewId !== message.viewId || view.revision !== message.revision) {
			return;
		}
		this.#ackedAttachIds.set(path, attachId);
		this.#flushPendingCallbacks(path);
	}

	#installSnapshot(path: string, view: ActiveView, snapshot: ViewSnapshot): void {
		const replacesView = view.viewId !== snapshot.viewId;
		view.viewId = snapshot.viewId;
		view.revision = snapshot.revision;
		if (replacesView) this.#deletePendingCallbacks(path);
		view.onInit(snapshot);
	}

	#requestResync(path: string): void {
		const attachId = this.#activeAttachIds.get(path);
		if (attachId && this.#ackedAttachIds.get(path) !== attachId) return;
		this.#sendAttach(path);
	}

	#queueCallback(message: ClientCallbackMessage): void {
		this.#reserveQueueSlot();
		const queue = this.#pendingCallbacks.get(message.path) ?? [];
		queue.push(message);
		this.#pendingCallbacks.set(message.path, queue);
		this.#pendingCallbackCount += 1;
	}

	#flushPendingCallbacks(path: string): void {
		if (!this.#activeViews.has(path) || !this.#isAttachAcked(path)) return;
		const queue = this.#pendingCallbacks.get(path);
		if (!queue) return;
		this.#pendingCallbacks.delete(path);
		this.#pendingCallbackCount -= queue.length;
		for (const message of queue) {
			this.sendMessage(message);
		}
	}

	#deletePendingCallbacks(path: string): void {
		const queue = this.#pendingCallbacks.get(path);
		if (!queue) return;
		this.#pendingCallbacks.delete(path);
		this.#pendingCallbackCount -= queue.length;
	}

	#reserveQueueSlot(): void {
		if (this.#messageQueue.length + this.#pendingCallbackCount < CLIENT_QUEUE_LIMIT) return;
		this.#queueOverflowed = true;
		this.#messageQueue = [];
		this.#pendingCallbacks.clear();
		this.#pendingCallbackCount = 0;
		this.#closeSocket();
		this.#setStatus("error");
		if (typeof window !== "undefined") window.location.reload();
		throw new Error(CLIENT_QUEUE_OVERFLOW_MESSAGE);
	}

	_ensureChannelEntry(id: string): {
		bridge: ChannelBridge;
		refCount: number;
	} {
		return this.#ensureChannelEntry(id);
	}
}
