import { useEffect, useState } from "react";
import type { PulseSocketIOClient } from "./client";
import type {
	ServerChannelEventMessage,
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
} from "./messages";
import { usePulseClient } from "./pulse";

export class PulseChannelResetError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PulseChannelResetError";
	}
}

/** A remote request handler failed (`ok: false`), as opposed to a transport reset. */
export class PulseChannelError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PulseChannelError";
	}
}

export class PulseChannelTimeoutError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PulseChannelTimeoutError";
	}
}

export type ChannelEventHandler = (payload: any) => any | Promise<any>;

interface PendingRequest {
	resolve: (value: any) => void;
	reject: (error: any) => void;
	timer?: ReturnType<typeof setTimeout>;
}

const MAX_BACKLOG_EVENTS = 1000;

export function createRandomId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID().replace(/-/g, "");
	}
	return Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
}

function formatError(error: unknown): string {
	// Must be total: a hostile toString()/toJSON() must not escape, since a
	// request handler owes the server exactly one response.
	try {
		if (error instanceof Error) return error.message;
		if (typeof error === "string") return error;
		// JSON.stringify returns undefined (not a string) for undefined,
		// functions, and symbols; the wire requires a real string.
		const text: string | undefined = JSON.stringify(error);
		return text ?? String(error);
	} catch {
		try {
			return String(error);
		} catch {
			return "Unserializable error";
		}
	}
}

export class ChannelBridge {
	private handlers = new Map<string, Set<ChannelEventHandler>>();
	private pending = new Map<string, PendingRequest>();
	private backlog: ServerChannelEventMessage[] = [];
	private closed = false;
	private epoch = 0;

	constructor(
		private client: PulseSocketIOClient,
		public readonly id: string,
	) {}

	emit(event: string, payload: any = null): void {
		this.ensureOpen();
		this.client.sendMessage({
			type: "channel_event",
			channel: this.id,
			event,
			payload: payload === undefined ? null : payload,
		});
	}

	request(
		event: string,
		payload: any = null,
		options?: { timeoutMs?: number },
	): Promise<any> {
		this.ensureOpen();
		const requestId = createRandomId();
		return new Promise((resolve, reject) => {
			const entry: PendingRequest = { resolve, reject };
			const timeoutMs = options?.timeoutMs;
			if (timeoutMs !== undefined) {
				entry.timer = setTimeout(() => {
					this.pending.delete(requestId);
					reject(new PulseChannelTimeoutError("Channel request timed out"));
				}, timeoutMs);
			}
			this.pending.set(requestId, entry);
			this.client.sendMessage({
				type: "channel_request",
				channel: this.id,
				event,
				requestId,
				payload: payload === undefined ? null : payload,
			});
		});
	}

	on(event: string, handler: ChannelEventHandler): () => void {
		this.ensureOpen();
		let bucket = this.handlers.get(event);
		if (!bucket) {
			bucket = new Set();
			this.handlers.set(event, bucket);
		}
		bucket.add(handler);
		this.flushBacklog(event);
		return () => {
			const set = this.handlers.get(event);
			if (!set) return;
			set.delete(handler);
			if (set.size === 0) {
				this.handlers.delete(event);
			}
		};
	}

	handleServerMessage(message: ServerChannelMessage): boolean {
		if (message.type === "channel_response") {
			this.resolvePending(message);
			return this.closed;
		}
		if (this.closed) {
			return true;
		}
		if (message.type === "channel_event" && message.event === "__close__") {
			this.dispose(new PulseChannelResetError("Channel closed by server"));
			return true;
		}
		if (message.type === "channel_request") {
			void this.dispatchRequest(message);
		} else {
			this.dispatchEvent(message);
		}
		return this.closed;
	}

	/**
	 * Transport-level disconnect. The bridge is identity-scoped and mounted
	 * hooks keep referencing it, so it must stay usable across reconnects:
	 * reject in-flight requests and drop the backlog, but keep handlers and
	 * stay open.
	 */
	resetForReconnect(reason: PulseChannelResetError): void {
		this.epoch += 1;
		this.rejectPending(reason);
		this.backlog = [];
	}

	dispose(reason: PulseChannelResetError): void {
		if (this.closed) {
			return;
		}
		this.closed = true;
		this.epoch += 1;
		this.rejectPending(reason);
		this.handlers.clear();
		this.backlog = [];
		// Registry lifecycle is managed by the owning client.
	}

	private rejectPending(reason: PulseChannelResetError): void {
		for (const request of this.pending.values()) {
			if (request.timer !== undefined) {
				clearTimeout(request.timer);
			}
			request.reject(reason);
		}
		this.pending.clear();
	}

	private ensureOpen(): void {
		if (this.closed) {
			throw new PulseChannelResetError("Channel is closed");
		}
	}

	private flushBacklog(event: string): void {
		if (this.backlog.length === 0) return;
		const remaining: ServerChannelEventMessage[] = [];
		for (const item of this.backlog) {
			if (item.event === event) {
				this.dispatchEvent(item);
			} else {
				remaining.push(item);
			}
		}
		this.backlog = remaining;
	}

	private dispatchEvent(message: ServerChannelEventMessage): void {
		const handlers = this.handlers.get(message.event);
		if (!handlers || handlers.size === 0) {
			if (this.backlog.length >= MAX_BACKLOG_EVENTS) {
				const dropped = this.backlog.shift();
				console.warn(
					`Pulse channel '${this.id}' backlog full; dropping oldest '${dropped?.event}' event`,
				);
			}
			this.backlog.push(message);
			return;
		}
		for (const handler of handlers) {
			try {
				const result = handler(message.payload);
				if (result && typeof (result as Promise<any>).then === "function") {
					void (result as Promise<any>).catch((err) => {
						console.error("Pulse channel handler error", err);
					});
				}
			} catch (err) {
				console.error("Pulse channel handler error", err);
			}
		}
	}

	private async dispatchRequest(message: ServerChannelRequestMessage): Promise<void> {
		// The server cancels in-flight requests on disconnect; a response
		// resolved after a reset would answer a request that no longer exists.
		const epoch = this.epoch;
		let response: any;
		let error: unknown;
		let failed = false;
		try {
			const handlers = this.handlers.get(message.event);
			if (handlers && handlers.size > 0) {
				for (const handler of handlers) {
					response = await Promise.resolve(handler(message.payload));
					// null falls through to the next handler, matching Python's
					// None (undefined does not exist on the wire).
					if (response !== undefined && response !== null) break;
				}
			}
		} catch (err) {
			error = err;
			failed = true;
		}
		if (this.closed || this.epoch !== epoch) {
			return;
		}
		if (failed) {
			this.client.sendMessage({
				type: "channel_response",
				channel: this.id,
				responseTo: message.requestId,
				ok: false,
				error: formatError(error),
			});
			return;
		}
		this.client.sendMessage({
			type: "channel_response",
			channel: this.id,
			responseTo: message.requestId,
			ok: true,
			payload: response === undefined ? null : response,
		});
	}

	private resolvePending(message: ServerChannelResponseMessage): void {
		const entry = this.pending.get(message.responseTo);
		if (!entry) {
			return;
		}
		this.pending.delete(message.responseTo);
		if (entry.timer !== undefined) {
			clearTimeout(entry.timer);
		}
		// Validate the discriminant exactly, once, at the edge; both runtimes
		// use strict equality so e.g. ok=0 means the same thing everywhere.
		if (message.ok === true) {
			entry.resolve(message.payload);
		} else if (message.ok === false && typeof message.error === "string") {
			entry.reject(new PulseChannelError(message.error));
		} else {
			entry.reject(new PulseChannelResetError("Malformed channel response"));
		}
	}
}

export function usePulseChannel(channelId: string): ChannelBridge | null {
	const client = usePulseClient();

	const [bridge, setBridge] = useState<ChannelBridge | null>(null);

	useEffect(() => {
		if (!channelId) {
			throw new Error("usePulseChannel requires a non-empty channelId");
		}
		const acquired = client.acquireChannel(channelId);
		setBridge(acquired);
		return () => {
			setBridge((current) => (current === acquired ? null : current));
			client.releaseChannel(channelId);
		};
	}, [client, channelId]);

	return bridge;
}
