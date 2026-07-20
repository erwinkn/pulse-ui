import { describe, expect, it, vi } from "bun:test";
import { ChannelBridge, PulseChannelResetError } from "./channel";
import { PulseSocketIOClient } from "./client";
import type { ClientChannelMessage } from "./messages";

function makeClient() {
	const sent: ClientChannelMessage[] = [];
	const sendMessage = vi.fn(async (message: ClientChannelMessage) => {
		sent.push(message);
	});
	const client = { sendMessage } as any;
	const bridge = new ChannelBridge(client, "chan-1");
	return { bridge, sent, sendMessage };
}

describe("ChannelBridge", () => {
	it("queues request and resolves on response", async () => {
		const { bridge, sent } = makeClient();
		const pending = bridge.request("echo", { foo: 1 });
		expect(sent).toHaveLength(1);
		const requestId = sent[0]!.requestId!;
		bridge.handleServerMessage({
			type: "channel_message",
			channel: "chan-1",
			responseTo: requestId,
			payload: { foo: 2 },
		});
		await expect(pending).resolves.toEqual({ foo: 2 });
	});

	it("dispatches events to registered handlers", () => {
		const { bridge } = makeClient();
		const handler = vi.fn();
		bridge.on("ping", handler);
		bridge.handleServerMessage({
			type: "channel_message",
			channel: "chan-1",
			event: "ping",
			payload: { value: 42 },
		});
		expect(handler).toHaveBeenCalledWith({ value: 42 });
	});

	it("responds to server requests", async () => {
		const { bridge, sendMessage } = makeClient();
		bridge.on("compute", () => 99);
		bridge.handleServerMessage({
			type: "channel_message",
			channel: "chan-1",
			event: "compute",
			requestId: "req-1",
			payload: {},
		});
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(sendMessage).toHaveBeenCalledWith(
			expect.objectContaining({
				responseTo: "req-1",
				payload: 99,
				event: undefined,
			}),
		);
	});

	it("rejects pending requests when closed", async () => {
		const { bridge } = makeClient();
		const pending = bridge.request("close-me");
		bridge.handleServerMessage({
			type: "channel_message",
			channel: "chan-1",
			event: "__close__",
		});
		await expect(pending).rejects.toBeInstanceOf(PulseChannelResetError);
	});

	it("reacquires a fresh bridge after release closes a channel", () => {
		const client = new PulseSocketIOClient(
			{},
			vi.fn() as any,
			{
				initialConnectingDelay: 0,
				initialErrorDelay: 0,
				reconnectErrorDelay: 0,
			},
		);

		const first = client.acquireChannel("chan-1");
		client.releaseChannel("chan-1");

		expect(() => first.on("event", vi.fn())).toThrow(PulseChannelResetError);

		const second = client.acquireChannel("chan-1");
		expect(second).not.toBe(first);
		expect(() => second.on("event", vi.fn())).not.toThrow();
	});
});
