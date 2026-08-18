import { describe, expect, it, vi } from "bun:test";
import {
	ChannelBridge,
	PulseChannelDetachedError,
	PulseChannelDisconnectedError,
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
		requestChannel(requestId: string, message: ClientChannelMessage) {
			return new Promise((resolve, reject) => {
				pending.set(requestId, { resolve, reject });
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
	it("emits mailbox events without lifecycle traffic", () => {
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

	it("raises on() after detach and still emits", () => {
		const { bridge, sent } = makeBridgeClient();
		bridge.detach();
		expect(() => bridge.on("event", vi.fn())).toThrow(PulseChannelDetachedError);
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
		expect(() => bridge.on("other", vi.fn())).toThrow(PulseChannelDetachedError);
		bridge.attach();
		expect(() => bridge.on("other", vi.fn())).not.toThrow();
		bridge.dispatchEvent("ping", 1);
		expect(handler).toHaveBeenCalledWith(1);
	});
});
