import { describe, expect, it, vi } from "bun:test";
import {
	ChannelBridge,
	PulseChannelDisconnectedError,
	PulseChannelDetachedError,
	PulseChannelTimeoutError,
} from "./channel";
import type { ClientChannelMessage } from "./messages";

function makeBridgeClient(connected = true) {
	const sent: ClientChannelMessage[] = [];
	const pending = new Map<string, { resolve: (value: any) => void; reject: (error: any) => void }>();
	const client = {
		isConnected: () => connected,
		sendMessage: vi.fn((message: ClientChannelMessage) => {
			sent.push(message);
		}),
		attachHandle: vi.fn(),
		detachHandle: vi.fn(),
		requestChannel(
			requestId: string,
			message: ClientChannelMessage,
			_owner: ChannelBridge,
			timeout?: number,
		) {
			return new Promise((resolve, reject) => {
				pending.set(requestId, { resolve, reject });
				if (timeout !== undefined) {
					setTimeout(() => {
						if (!pending.has(requestId)) return;
						pending.delete(requestId);
						reject(new PulseChannelTimeoutError(timeout, (message as { event: string }).event));
					}, timeout);
				}
				client.sendMessage(message);
			});
		},
		resolve(requestId: string, payload: any) {
			pending.get(requestId)?.resolve(payload);
		},
	};
	const bridge = new ChannelBridge(client as any, "chan-1");
	bridge.attach();
	return { bridge, sent, client };
}

describe("ChannelBridge", () => {
	it("emits channel events without lifecycle traffic", () => {
		const { bridge, sent } = makeBridgeClient();
		bridge.emit("ping", { foo: 1 });
		expect(sent).toEqual([
			{
				type: "channel",
				action: "event",
				channel: "chan-1",
				event: "ping",
				payload: { foo: 1 },
			},
		]);
	});

	it("queues request and resolves on client pending", async () => {
		const { bridge, sent, client } = makeBridgeClient();
		const pending = bridge.request("echo", { foo: 1 });
		expect(sent[0]).toMatchObject({
			type: "channel",
			action: "request",
			channel: "chan-1",
			event: "echo",
		});
		const requestId = (sent[0] as { requestId: string }).requestId;
		client.resolve(requestId, { foo: 2 });
		await expect(pending).resolves.toEqual({ foo: 2 });
	});

	it("fails request immediately when disconnected", async () => {
		const { bridge, sent } = makeBridgeClient(false);
		await expect(bridge.request("echo")).rejects.toBeInstanceOf(PulseChannelDisconnectedError);
		expect(sent).toEqual([]);
	});

	it("times out an optional request timeout", async () => {
		const { bridge } = makeBridgeClient();
		await expect(bridge.request("echo", undefined, { timeout: 1 })).rejects.toBeInstanceOf(
			PulseChannelTimeoutError,
		);
	});

	it("times out unanswered requests after the default timeout", async () => {
		vi.useFakeTimers();
		try {
			const { bridge } = makeBridgeClient();
			const pending = bridge.request("echo");
			vi.advanceTimersByTime(30_000);
			await expect(pending).rejects.toBeInstanceOf(PulseChannelTimeoutError);
		} finally {
			vi.useRealTimers();
		}
	});

	it("keeps on() legal after detach and still emits", () => {
		const { bridge, sent } = makeBridgeClient();
		const handler = vi.fn();
		bridge.detach();
		expect(() => bridge.on("event", handler)).not.toThrow();
		bridge.emit("still-routes", 1);
		expect(sent[0]).toMatchObject({
			type: "channel",
			action: "event",
			event: "still-routes",
		});
	});

	it("reattaches the same handle after StrictMode detach", () => {
		const { bridge } = makeBridgeClient();
		const handler = vi.fn();
		bridge.on("ping", handler);
		bridge.detach();
		expect(() => bridge.on("other", vi.fn())).not.toThrow();
		bridge.attach();
		bridge.dispatchEvent("ping", 1);
		expect(handler).toHaveBeenCalledWith(1);
	});

	it("registers the same handler only once", () => {
		const { bridge } = makeBridgeClient();
		const handler = vi.fn();
		bridge.on("ping", handler);
		bridge.on("ping", handler);
		bridge.dispatchEvent("ping", 1);
		expect(handler).toHaveBeenCalledTimes(1);
	});

	it("keeps a duplicate registration after removing one disposer", () => {
		const { bridge } = makeBridgeClient();
		const handler = vi.fn();
		const removeFirst = bridge.on("ping", handler);
		bridge.on("ping", handler);
		removeFirst();
		bridge.dispatchEvent("ping", 1);
		expect(handler).toHaveBeenCalledTimes(1);
		removeFirst();
		bridge.dispatchEvent("ping", 2);
		expect(handler).toHaveBeenCalledTimes(2);
	});

	it("warns once when emitting from a detached bridge", () => {
		const { bridge } = makeBridgeClient();
		const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
		bridge.emit("beforeAttach");
		bridge.detach();
		bridge.emit("afterDetach");
		expect(warning).toHaveBeenCalledTimes(1);
		warning.mockRestore();
	});
});
