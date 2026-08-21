import { useEffect, useMemo } from "react";
import type { PulseSocketIOClient } from "./client";
import type { ChannelErrorCode } from "./messages";
import { usePulseClient } from "./pulse";

export class PulseChannelDetachedError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PulseChannelDetachedError";
	}
}

export class PulseChannelDisconnectedError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PulseChannelDisconnectedError";
	}
}

export class PulseChannelRemoteError extends Error {
	code: ChannelErrorCode;

	constructor(code: ChannelErrorCode, message: string) {
		super(`${code}: ${message}`);
		this.name = "PulseChannelRemoteError";
		this.code = code;
	}
}

export class PulseChannelTimeoutError extends Error {
	timeout: number;
	event: string;

	constructor(timeout: number, event: string) {
		super(`Channel request timed out after ${timeout}ms: ${event}`);
		this.name = "PulseChannelTimeoutError";
		this.timeout = timeout;
		this.event = event;
	}
}

export type ChannelEventHandler = (payload: any) => any | Promise<any>;

export type ChannelRequestOptions = {
	timeout?: number;
};

const DEFAULT_CHANNEL_REQUEST_TIMEOUT = 30_000;

export function createRandomId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID().replace(/-/g, "");
	}
	return Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
}

export class ChannelBridge {
	#handlers = new Map<string, Map<ChannelEventHandler, number>>();
	#detached = false;
	#attached = false;
	#warnedAboutDetachedEmit = false;

	constructor(
		private client: PulseSocketIOClient,
		public readonly id: string,
	) {}

	attach(): void {
		if (this.#attached) return;
		this.#detached = false;
		this.#attached = true;
		this.client.attachHandle(this);
	}

	detach(): void {
		if (!this.#attached && this.#detached) return;
		this.#attached = false;
		this.#detached = true;
		this.client.detachHandle(this);
	}

	emit(event: string, payload?: any): void {
		const message: {
			type: "channel";
			action: "event";
			channel: string;
			event: string;
			payload?: any;
		} = {
			type: "channel",
			action: "event",
			channel: this.id,
			event,
		};
		if (payload !== undefined) {
			message.payload = payload;
		}
		if ((!this.#attached || this.#detached) && !this.#warnedAboutDetachedEmit) {
			this.#warnedAboutDetachedEmit = true;
			console.warn(`Pulse channel ${this.id} emitted while detached`);
		}
		this.client.sendMessage(message);
	}

	request(event: string, payload?: any, options?: ChannelRequestOptions): Promise<any> {
		if (!this.client.isConnected()) {
			return Promise.reject(new PulseChannelDisconnectedError("No render session is connected"));
		}
		const requestId = createRandomId();
		const message: {
			type: "channel";
			action: "request";
			channel: string;
			event: string;
			requestId: string;
			payload?: any;
		} = {
			type: "channel",
			action: "request",
			channel: this.id,
			event,
			requestId,
		};
		if (payload !== undefined) {
			message.payload = payload;
		}
		return this.client.requestChannel(
			requestId,
			message,
			this,
			options?.timeout ?? DEFAULT_CHANNEL_REQUEST_TIMEOUT,
		);
	}

	on(event: string, handler: ChannelEventHandler): () => void {
		let bucket = this.#handlers.get(event);
		if (!bucket) {
			bucket = new Map();
			this.#handlers.set(event, bucket);
		}
		bucket.set(handler, (bucket.get(handler) ?? 0) + 1);
		let removed = false;
		return () => {
			if (removed) return;
			removed = true;
			const set = this.#handlers.get(event);
			if (!set) return;
			const count = set.get(handler);
			if (count === undefined) return;
			if (count === 1) {
				set.delete(handler);
			} else {
				set.set(handler, count - 1);
			}
			if (set.size === 0) {
				this.#handlers.delete(event);
			}
		};
	}

	hasHandler(event: string): boolean {
		const handlers = this.#handlers.get(event);
		return !!handlers && handlers.size > 0;
	}

	dispatchEvent(event: string, payload: any): void {
		if (this.#detached || !this.#attached) return;
		const handlers = this.#handlers.get(event);
		if (!handlers) return;
		for (const handler of handlers.keys()) {
			try {
				const result = handler(payload);
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

	async dispatchRequest(event: string, payload: any): Promise<any> {
		const handlers = this.#handlers.get(event);
		if (!handlers || handlers.size === 0) {
			return undefined;
		}
		const handler = handlers.keys().next().value;
		if (!handler) {
			return undefined;
		}
		return await Promise.resolve(handler(payload));
	}
}

export function useChannel(channelId: string): ChannelBridge {
	if (!channelId) {
		throw new Error("useChannel requires a non-empty channelId");
	}
	const client = usePulseClient();
	const bridge = useMemo(() => client.channel(channelId), [client, channelId]);
	useEffect(() => {
		bridge.attach();
		return () => {
			bridge.detach();
		};
	}, [bridge]);
	return bridge;
}
