import type { PulseSocketIOClient } from "./client";
import type {
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
} from "./messages";

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
		return JSON.stringify(error);
	} catch {
		return String(error);
	}
}

function isServerResponseMessage(
	message: ServerChannelMessage,
): message is ServerChannelResponseMessage {
	return typeof (message as ServerChannelResponseMessage).responseTo === "string";
}

function isServerRequestMessage(
	message: ServerChannelMessage,
): message is ServerChannelRequestMessage {
	return typeof (message as ServerChannelRequestMessage).event === "string";
}

export class ChannelBridge {
	private handlers = new Map<string, Set<ChannelEventHandler>>();
	private pending = new Map<string, PendingRequest>();
	private backlog: ServerChannelRequestMessage[] = [];
	private closed = false;

	constructor(
		private client: PulseSocketIOClient,
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
		const requestId = randomId();
		return new Promise((resolve, reject) => {
			this.pending.set(requestId, { resolve, reject });
			this.client.sendMessage({
				type: "channel_message",
				channel: this.id,
				event,
				payload,
				requestId,
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
		if (isServerResponseMessage(message)) {
			this.resolvePending(message);
			return this.closed;
		}
		if (this.closed) {
			return true;
		}
		if (!isServerRequestMessage(message)) {
			return this.closed;
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
		if (error) {
			this.client.sendMessage({
				type: "channel_message",
				channel: this.id,
				event: undefined,
				responseTo: message.requestId,
				error: formatError(error),
			});
			return;
		}
		this.client.sendMessage({
			type: "channel_message",
			channel: this.id,
			event: undefined,
			responseTo: message.requestId,
			payload: response,
		});
	}

	private resolvePending(message: ServerChannelResponseMessage): void {
		const entry = message.responseTo ? this.pending.get(message.responseTo) : undefined;
		if (!entry) {
			return;
		}
		this.pending.delete(message.responseTo!);
		if (message.error !== undefined && message.error !== null) {
			entry.reject(new PulseChannelResetError(String(message.error)));
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

export function createChannelBridge(client: PulseSocketIOClient, id: string): ChannelBridge {
	return new ChannelBridge(client, id);
}
