import { useEffect, useState } from "react";
import type { ClientMessage, ReplyMessage, ServerChannelRequestMessage } from "./messages";
import { usePulseClient } from "./pulse";

export class PulseChannelResetError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PulseChannelResetError";
	}
}

export type ChannelEventHandler = (payload: any) => any | Promise<any>;

export interface ChannelHost {
	sendMessage(message: ClientMessage): void | Promise<void>;
	replies: {
		register(id: string): Promise<any>;
		reject(id: string, error: unknown): void;
	};
}

export function createRandomId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID().replace(/-/g, "");
	}
	return Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
}

function formatError(error: unknown): string {
	if (error instanceof Error) return error.message;
	if (typeof error === "string") return error;
	try {
		return JSON.stringify(error);
	} catch {
		return String(error);
	}
}

export class ChannelBridge {
	private handlers = new Map<string, Set<ChannelEventHandler>>();
	private pendingIds = new Set<string>();
	private backlog: ServerChannelRequestMessage[] = [];
	private closed = false;

	constructor(
		private client: ChannelHost,
		public readonly id: string,
	) {}

	emit(event: string, payload?: any): void {
		this.ensureOpen();
		this.client.sendMessage({
			type: "channel_message",
			channel: this.id,
			event,
			payload,
		});
	}

	request(event: string, payload?: any): Promise<any> {
		this.ensureOpen();
		const requestId = createRandomId();
		this.pendingIds.add(requestId);
		const pending = this.client.replies.register(requestId);
		this.client.sendMessage({
			type: "channel_message",
			channel: this.id,
			event,
			payload,
			requestId,
		});
		return pending.finally(() => {
			this.pendingIds.delete(requestId);
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

	handleServerMessage(message: ServerChannelRequestMessage): boolean {
		if (this.closed) {
			return true;
		}

		if (message.event === "__close__") {
			this.close(new PulseChannelResetError("Channel closed by server"));
			return true;
		}
		if (message.requestId) {
			void this.dispatchRequest(
				message as ServerChannelRequestMessage & {
					requestId: string;
				},
			);
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
		const remaining: ServerChannelRequestMessage[] = [];
		for (const item of this.backlog) {
			if (item.event === event) {
				this.dispatchEvent(item);
			} else {
				remaining.push(item);
			}
		}
		this.backlog = remaining;
	}

	private dispatchEvent(message: ServerChannelRequestMessage): void {
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

	private async dispatchRequest(
		message: ServerChannelRequestMessage & { requestId: string },
	): Promise<void> {
		const handlers = this.handlers.get(message.event);
		let response: any;
		let error: any;
		if (handlers && handlers.size > 0) {
			for (const handler of handlers) {
				try {
					const result = handler(message.payload);
					response = await Promise.resolve(result);
					if (response !== undefined) {
						break;
					}
				} catch (err) {
					error = err;
					break;
				}
			}
		}
		const reply: ReplyMessage =
			error !== undefined
				? { type: "reply", id: message.requestId, error: formatError(error) }
				: { type: "reply", id: message.requestId, payload: response };
		this.client.sendMessage(reply);
	}

	private close(reason: PulseChannelResetError): void {
		if (this.closed) {
			return;
		}
		this.closed = true;
		for (const id of this.pendingIds) {
			this.client.replies.reject(id, reason);
		}
		this.pendingIds.clear();
		this.handlers.clear();
		this.backlog = [];
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
