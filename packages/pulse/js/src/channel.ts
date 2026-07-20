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

export type ChannelEventHandler = (payload: any) => any | Promise<any>;

interface PendingRequest {
	resolve: (value: any) => void;
	reject: (error: any) => void;
}

function randomId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID().replace(/-/g, "");
	}
	return Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
}

function formatError(error: unknown): string {
	if (error instanceof Error) return error.message;
	if (typeof error === "string") return error;
	try {
		// JSON.stringify returns undefined (not a string) for undefined,
		// functions, and symbols; the wire requires a real string.
		const text: string | undefined = JSON.stringify(error);
		return text ?? String(error);
	} catch {
		return String(error);
	}
}

export class ChannelBridge {
	private handlers = new Map<string, Set<ChannelEventHandler>>();
	private pending = new Map<string, PendingRequest>();
	private backlog: ServerChannelEventMessage[] = [];
	private closed = false;

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

	request(event: string, payload: any = null): Promise<any> {
		this.ensureOpen();
		const requestId = randomId();
		return new Promise((resolve, reject) => {
			this.pending.set(requestId, { resolve, reject });
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
			this.close(new PulseChannelResetError("Channel closed by server"));
			return true;
		}
		if (message.type === "channel_request") {
			void this.dispatchRequest(message);
		} else {
			this.dispatchEvent(message);
		}
		return this.closed;
	}

	handleDisconnect(reason: PulseChannelResetError): void {
		this.close(reason);
	}

	dispose(reason: PulseChannelResetError): void {
		this.close(reason);
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
		const handlers = this.handlers.get(message.event);
		let response: any;
		let error: unknown;
		let failed = false;
		if (handlers && handlers.size > 0) {
			for (const handler of handlers) {
				try {
					response = await Promise.resolve(handler(message.payload));
					if (response !== undefined) break;
				} catch (err) {
					error = err;
					failed = true;
					break;
				}
			}
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
		if (!message.ok) {
			entry.reject(new PulseChannelResetError(message.error));
		} else {
			entry.resolve(message.payload);
		}
	}

	private close(reason: PulseChannelResetError): void {
		if (this.closed) {
			return;
		}
		this.closed = true;
		for (const request of this.pending.values()) {
			request.reject(reason);
		}
		this.pending.clear();
		this.handlers.clear();
		this.backlog = [];
		// No-op: owning client manages registry lifecycle.
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
