import { describe, expect, it, vi } from "bun:test";
import { ChannelBridge, PulseChannelResetError } from "./channel";
import { PulseSocketIOClient } from "./client";
import type { ClientMessage } from "./messages";
import { createPendingReplies } from "./replies";

function makeClient() {
	const sent: ClientMessage[] = [];
	const sendMessage = vi.fn(async (message: ClientMessage) => {
		sent.push(message);
	});
	const client = {
		sendMessage,
		replies: createPendingReplies(),
	};
	const bridge = new ChannelBridge(client, "chan-1");
	return { bridge, sent, sendMessage, client };
}

describe("ChannelBridge", () => {
	it("queues request and resolves on reply", async () => {
		const { bridge, sent, client } = makeClient();
		const pending = bridge.request("echo", { foo: 1 });
		expect(sent).toHaveLength(1);
		const request = sent[0];
		expect(request).toMatchObject({ type: "channel_message", event: "echo" });
		const requestId = request && "requestId" in request ? request.requestId : undefined;
		expect(requestId).toBeDefined();
		client.replies.apply({
			type: "reply",
			id: requestId!,
			payload: { foo: 2 },
		});
		await expect(pending).resolves.toEqual({ foo: 2 });
	});

	it("rejects wire errors as Error, not PulseChannelResetError", async () => {
		const { bridge, sent, client } = makeClient();
		const pending = bridge.request("boom");
		const request = sent[0];
		const requestId = request && "requestId" in request ? request.requestId : undefined;
		client.replies.apply({
			type: "reply",
			id: requestId!,
			error: "handler failed",
		});
		await expect(pending).rejects.toThrow("handler failed");
		await pending.catch((error: unknown) => {
			expect(error).toBeInstanceOf(Error);
			expect(error).not.toBeInstanceOf(PulseChannelResetError);
		});
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

	it("responds to server requests with a reply", async () => {
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
		expect(sendMessage).toHaveBeenCalledWith({
			type: "reply",
			id: "req-1",
			payload: 99,
		});
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
			"http://pulse.test",
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
