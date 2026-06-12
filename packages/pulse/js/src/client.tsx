import type { NavigateFunction } from "react-router";
import { io, type Socket } from "socket.io-client";
import { ChannelBridge, PulseChannelResetError } from "./channel";
import type { RouteInfo } from "./helpers";
import type {
	ClientApiResultMessage,
	ClientCallbackMessage,
	ClientJsResultMessage,
	ClientMessage,
	ClientResumeMessage,
	ServerApiCallMessage,
	ServerChannelMessage,
	ServerError,
	ServerJsExecMessage,
	ServerMessage,
	ServerResumeMessage,
} from "./messages";
import type { PulsePrerenderView } from "./pulse";
import { extractEvent } from "./serialize/events";
import { deserialize, serialize, type Serialized } from "./serialize/serializer";
import type { VDOMUpdate } from "./vdom";

function documentIsHidden(): boolean {
	return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function browserIsOnline(): boolean {
	return typeof navigator === "undefined" || navigator.onLine !== false;
}

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
	onInit: (view: PulsePrerenderView) => void;
	onUpdate: (ops: VDOMUpdate[]) => void;
	onJsExec: (msg: ServerJsExecMessage) => void;
	onServerError: (error: ServerError) => void;
	deserializeMessage: (data: Serialized) => ServerMessage;
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
	updateRoute(viewId: string, routeInfo: RouteInfo): void;
	invokeCallback(viewId: string, callback: string, args: any[]): void;
	// VDOM subscription
	attach(viewId: string, view: MountedView): void;
	detach(viewId: string): void;
}

export class PulseSocketIOClient {
	#activeViews: Map<string, MountedView>;
	#activeAttachIds: Map<string, string>;
	#ackedAttachIds: Map<string, string>;
	#pendingCallbacks: Map<string, ClientCallbackMessage[]>;
	#socket: Socket | null = null;
	#messageQueue: ClientMessage[];
	#connectionListeners: Set<ConnectionStatusListener> = new Set();
	#channels: Map<string, { view: string; bridge: ChannelBridge }> = new Map();
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
	#resumePending = false;
	#pendingResumeId: string | null = null;

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
				if (this.#hasConnectedOnce) {
					// The transport is up; the resume handshake completes at the
					// protocol level and flips the status back to "ok".
					this.#startResume(socket);
					resolve();
					return;
				}
				// Send attach for all active views on connect/reconnect
				for (const [viewId, view] of this.#activeViews) {
					this.#sendAttach(viewId, view.routeInfo, socket);
				}
				for (const [channel, endpoint] of this.#channels) {
					socket.emit(
						"message",
						serialize({
							type: "channel_connect",
							channel,
							view: endpoint.view,
						}),
					);
				}

				for (const payload of this.#messageQueue) {
					// Already sent above
					if (payload.type === "attach" && this.#activeViews.has(payload.view)) {
						continue;
					}
					if (
						payload.type === "channel_connect" ||
						payload.type === "channel_disconnect"
					) {
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
			});

			// Wrap in an arrow function to avoid losing the `this` reference
			socket.on("message", (data) => {
				if (this.#socket !== socket) return;
				this.#handleSerializedServerMessage(data);
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
		if (this.isConnected() && !this.#resumePending) {
			// console.log("[SocketIOTransport] Sending:", payload);
			this.#socket!.emit("message", serialize(payload as any));
		} else {
			// console.log("[SocketIOTransport] Queuing message:", payload);
			this.#messageQueue.push(payload);
		}
	}

	public attach(viewId: string, view: MountedView) {
		if (this.#activeViews.has(viewId)) {
			throw new Error(`View ${viewId} is already attached`);
		}
		this.#activeViews.set(viewId, view);
		this.#sendAttach(viewId, view.routeInfo);
	}

	public updateRoute(viewId: string, routeInfo: RouteInfo) {
		const view = this.#activeViews.get(viewId);
		if (view) {
			view.routeInfo = routeInfo;
			this.sendMessage({
				type: "update",
				view: viewId,
				routeInfo,
			});
		}
	}

	public detach(viewId: string) {
		this.#activeViews.delete(viewId);
		this.#activeAttachIds.delete(viewId);
		this.#ackedAttachIds.delete(viewId);
		this.#pendingCallbacks.delete(viewId);
		for (const [channel, endpoint] of [...this.#channels]) {
			if (endpoint.view === viewId) {
				this.#releaseChannel(channel, endpoint);
			}
		}
		void this.sendMessage({ type: "detach", view: viewId });
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
		this.#connectionListeners.clear();
		this.#activeViews.clear();
		this.#activeAttachIds.clear();
		this.#ackedAttachIds.clear();
		this.#pendingCallbacks.clear();
		for (const { bridge } of this.#channels.values()) {
			bridge.dispose(new PulseChannelResetError("Client disconnected"));
		}
		this.#channels.clear();
		this.#currentStatus = "ok";
		this.#hasConnectedOnce = false;
		this.#resumePending = false;
		this.#pendingResumeId = null;
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
			case "vdom_init": {
				const view = this.#activeViews.get(message.view);
				// Ignore messages for views that are not mounted
				if (!view) return;
				view.onInit(message);
				break;
			}
			case "vdom_update": {
				const view = this.#activeViews.get(message.view);
				if (!view) return; // Not an active view; discard
				view.onUpdate(message.ops);
				break;
			}
			case "server_error": {
				if (message.view === undefined) {
					// Session-level error: surface on every active view.
					for (const view of this.#activeViews.values()) {
						view.onServerError(message.error);
					}
					break;
				}
				const view = this.#activeViews.get(message.view);
				if (!view) return; // discard for inactive views
				view.onServerError(message.error);
				break;
			}
			case "api_call": {
				void this.#performApiCall(message);
				break;
			}
			case "navigate_to": {
				if (message.sourceView) {
					const view = this.#activeViews.get(message.sourceView);
					if (!view) break;
					if (
						message.sourcePathname &&
						view.routeInfo.pathname !== message.sourcePathname
					) {
						break;
					}
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
			case "server_resume": {
				this.#handleServerResume(message);
				break;
			}
			case "attach_ack": {
				this.#handleAttachAck(message.view, message.attachId);
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

	public invokeCallback(viewId: string, callback: string, args: any[]) {
		if (!this.#activeViews.has(viewId)) return;
		const message: ClientCallbackMessage = {
			type: "callback",
			view: viewId,
			callback,
			args: args.map(extractEvent),
		};
		if (this.#isAttachAcked(viewId)) {
			this.sendMessage(message);
			return;
		}
		this.#queueCallback(message);
	}

	#handleJsExec(message: ServerJsExecMessage) {
		const view = this.#activeViews.get(message.view);
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

	public acquireChannel(id: string, viewId = ""): ChannelBridge {
		if (this.#channels.has(id)) {
			throw new Error(`Pulse channel '${id}' is already acquired`);
		}
		const bridge = new ChannelBridge(this, id, viewId);
		this.#channels.set(id, { view: viewId, bridge });
		this.sendMessage({
			type: "channel_connect",
			channel: id,
			view: viewId,
		});
		return bridge;
	}

	public releaseChannel(id: string, viewId = ""): void {
		const endpoint = this.#channels.get(id);
		if (!endpoint || endpoint.view !== viewId) {
			return;
		}
		this.#releaseChannel(id, endpoint);
	}

	#routeChannelMessage(message: ServerChannelMessage): void {
		const endpoint = this.#channels.get(message.channel);
		if (!endpoint) return;
		const closed = endpoint.bridge.handleServerMessage(message);
		if (closed) {
			this.#channels.delete(message.channel);
		}
	}

	#handleTransportDisconnect(): void {
		this.#ackedAttachIds.clear();
		this.#resumePending = false;
		this.#pendingResumeId = null;
		for (const entry of this.#channels.values()) {
			entry.bridge.handleDisconnect(new PulseChannelResetError("Connection lost"));
		}
	}

	#startResume(socket: Socket): void {
		const resumeId = `${Date.now()}:${Math.random().toString(16).slice(2)}`;
		this.#resumePending = true;
		this.#pendingResumeId = resumeId;
		const views: ClientResumeMessage["views"] = [];
		for (const [viewId, view] of this.#activeViews) {
			const attachId = this.#activeAttachIds.get(viewId);
			views.push({
				view: viewId,
				routeInfo: view.routeInfo,
				...(attachId ? { attachId } : {}),
			});
		}
		const channels: ClientResumeMessage["channels"] = [];
		for (const [channel, endpoint] of this.#channels) {
			channels.push({ channel, view: endpoint.view });
		}
		socket.emit(
			"message",
			serialize({
				type: "client_resume",
				resumeId,
				views,
				channels,
			} satisfies ClientResumeMessage),
		);
	}

	#handleServerResume(message: ServerResumeMessage): void {
		if (message.resumeId !== this.#pendingResumeId) return;
		this.#pendingResumeId = null;
		if (message.status === "reload") {
			this.#resumePending = false;
			this.#messageQueue = [];
			this.#pendingCallbacks.clear();
			for (const [channel, endpoint] of this.#channels) {
				endpoint.bridge.dispose(new PulseChannelResetError("Resume rejected"));
				this.#channels.delete(channel);
			}
			window.location.reload();
			return;
		}

		const acceptedViews = new Set((message.views ?? []).map((view) => view.view));
		const acceptedChannels = new Map(
			(message.channels ?? []).map((channel) => [channel.channel, channel.view]),
		);

		for (const viewId of [...this.#pendingCallbacks.keys()]) {
			if (!acceptedViews.has(viewId)) {
				this.#pendingCallbacks.delete(viewId);
			}
		}
		for (const view of message.views ?? []) {
			const attachId = view.attachId ?? this.#activeAttachIds.get(view.view);
			if (attachId && this.#activeAttachIds.get(view.view) === attachId) {
				this.#ackedAttachIds.set(view.view, attachId);
			}
		}
		for (const [channel, endpoint] of [...this.#channels]) {
			if (acceptedChannels.get(channel) !== endpoint.view) {
				endpoint.bridge.dispose(
					new PulseChannelResetError("Channel was not resumed"),
				);
				this.#channels.delete(channel);
			}
		}

		const queued = this.#messageQueue;
		this.#messageQueue = [];
		this.#resumePending = false;
		for (const viewId of acceptedViews) {
			this.#flushPendingCallbacks(viewId);
		}
		for (const payload of queued) {
			if (this.#shouldReplayAfterResume(payload, acceptedViews, acceptedChannels)) {
				this.sendMessage(payload);
			}
		}
		this.#handleConnected();
	}

	#shouldReplayAfterResume(
		payload: ClientMessage,
		acceptedViews: Set<string>,
		acceptedChannels: Map<string, string>,
	): boolean {
		if (
			payload.type === "attach" ||
			payload.type === "detach" ||
			payload.type === "update" ||
			payload.type === "channel_connect" ||
			payload.type === "channel_disconnect" ||
			payload.type === "client_resume"
		) {
			return false;
		}
		if (payload.type === "callback") {
			return acceptedViews.has(payload.view);
		}
		if (payload.type === "channel_message") {
			return acceptedChannels.has(payload.channel);
		}
		return true;
	}

	#handleSerializedServerMessage(data: Serialized): void {
		const raw = this.#serializedPayloadObject(data);
		if (raw) {
			const type = raw.type;
			if (type === "js_exec") {
				this.#handleSerializedJsExec(data, raw);
				return;
			}
			if (type === "channel_message") {
				if (this.#handleSerializedChannelMessage(data, raw)) {
					return;
				}
			}
		}
		this.#handleServerMessage(deserialize(data, { coerceNullsToUndefined: true }));
	}

	#handleSerializedJsExec(data: Serialized, raw: Record<string, unknown>): void {
		const viewId = raw.view;
		if (typeof viewId !== "string") {
			return;
		}
		const view = this.#activeViews.get(viewId);
		if (!view) {
			if (typeof raw.id === "string") this.#sendJsResult(raw.id, undefined, null);
			return;
		}
		this.#handleServerMessage(this.#deserializeForView(data, view, "js_exec", viewId));
	}

	#handleSerializedChannelMessage(
		data: Serialized,
		raw: Record<string, unknown>,
	): boolean {
		const viewId = raw.view;
		if (typeof viewId === "string") {
			const view = this.#activeViews.get(viewId);
			if (!view) {
				if (typeof raw.channel === "string") {
					this.#dropChannel(
						raw.channel,
						new PulseChannelResetError("Channel view is no longer active"),
					);
				}
				return true;
			}
			this.#handleServerMessage(
				this.#deserializeForView(data, view, "channel_message", viewId),
			);
			return true;
		}
		if (this.#hasPulseNodes(data)) {
			if (typeof raw.channel === "string") {
				this.#dropChannel(
					raw.channel,
					new PulseChannelResetError(
						"Route-bound channel message is missing an active view path",
					),
				);
			}
			return true;
		}
		return false;
	}

	#deserializeForView(
		data: Serialized,
		view: MountedView,
		type: string,
		viewId: string,
	): ServerMessage {
		try {
			return view.deserializeMessage(data);
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`[Pulse] Failed to deserialize ${type} for view '${viewId}': ${message}`);
		}
	}

	#serializedPayloadObject(data: Serialized): Record<string, unknown> | null {
		const raw = data[1];
		if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
			return null;
		}
		return raw as Record<string, unknown>;
	}

	#hasPulseNodes(data: Serialized): boolean {
		return data[0][4].length > 0;
	}

	#sendAttach(viewId: string, routeInfo: RouteInfo, socket?: Socket): void {
		const attachId = `${viewId}:${++this.#nextAttachId}`;
		this.#activeAttachIds.set(viewId, attachId);
		this.#ackedAttachIds.delete(viewId);
		const message = {
			type: "attach" as const,
			view: viewId,
			routeInfo,
			attachId,
		};
		if (socket) {
			socket.emit("message", serialize(message));
			return;
		}
		this.sendMessage(message);
	}

	#isAttachAcked(viewId: string): boolean {
		const attachId = this.#activeAttachIds.get(viewId);
		return attachId !== undefined && this.#ackedAttachIds.get(viewId) === attachId;
	}

	#handleAttachAck(viewId: string, attachId: string): void {
		if (this.#activeAttachIds.get(viewId) !== attachId) return;
		this.#ackedAttachIds.set(viewId, attachId);
		this.#flushPendingCallbacks(viewId);
	}

	#queueCallback(message: ClientCallbackMessage): void {
		const queue = this.#pendingCallbacks.get(message.view) ?? [];
		queue.push(message);
		this.#pendingCallbacks.set(message.view, queue);
	}

	#flushPendingCallbacks(viewId: string): void {
		if (!this.#activeViews.has(viewId) || !this.#isAttachAcked(viewId)) return;
		const queue = this.#pendingCallbacks.get(viewId);
		if (!queue) return;
		this.#pendingCallbacks.delete(viewId);
		for (const message of queue) {
			this.sendMessage(message);
		}
	}

	#releaseChannel(
		id: string,
		endpoint: { view: string; bridge: ChannelBridge },
	): void {
		this.#channels.delete(id);
		endpoint.bridge.dispose(new PulseChannelResetError("Channel released"));
		this.sendMessage({
			type: "channel_disconnect",
			channel: id,
		});
	}

	#dropChannel(id: string, reason: PulseChannelResetError): void {
		const entry = this.#channels.get(id);
		if (!entry) return;
		this.#channels.delete(id);
		entry.bridge.dispose(reason);
	}
}
