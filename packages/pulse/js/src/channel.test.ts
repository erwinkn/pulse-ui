import { describe, expect, it, vi } from "bun:test";
import { ChannelBridge, PulseChannelResetError } from "./channel";
import { PulseSocketIOClient } from "./client";
import type { ClientMessage } from "./messages";
import { PendingReplies } from "./replies";

function makeClient(channelId = "chan-1") {
	const sent: ClientMessage[] = [];
	const sendMessage = vi.fn((message: ClientMessage) => {
		sent.push(message);
	});
	const client = {
		sendMessage,
		replies: new PendingReplies(),
	};
	const bridge = new ChannelBridge(client, channelId);
	return { bridge, sent, sendMessage, client };
}

describe("PendingReplies", () => {
	it("mints unique ids and removes entries when they settle", async () => {
		const replies = new PendingReplies();
		const resolved = replies.pending({ cancelKey: "resolved" });
		const rejected = replies.pending();

		expect(resolved.id).not.toBe(rejected.id);
		replies.apply({
			type: "reply",
			id: resolved.id,
			payload: "done",
		});
		const error = new Error("failed");
		replies.reject(rejected.id, error);

		await expect(resolved.promise).resolves.toBe("done");
		await expect(rejected.promise).rejects.toBe(error);

		replies.rejectWhere("resolved", new Error("stale"));
		await expect(resolved.promise).resolves.toBe("done");
	});

	it("rejects only entries in the matching cancellation group", async () => {
		const replies = new PendingReplies();
		const firstChannel = replies.pending({ cancelKey: "chan-1" });
		const secondChannel = replies.pending({ cancelKey: "chan-2" });
		const error = new Error("channel closed");

		replies.rejectWhere("chan-1", error);
		await expect(firstChannel.promise).rejects.toBe(error);

		let secondSettled = false;
		void secondChannel.promise.then(
			() => {
				secondSettled = true;
			},
			() => {
				secondSettled = true;
			},
		);
		await Promise.resolve();
		expect(secondSettled).toBe(false);

		replies.rejectWhere("chan-2", error);
		await expect(secondChannel.promise).rejects.toBe(error);
	});
});

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

	it("rejects and clears pending registration when sending throws", async () => {
		const { bridge, client, sendMessage } = makeClient();
		const error = new Error("serialize failed");
		const reject = vi.spyOn(client.replies, "reject");
		sendMessage.mockImplementationOnce(() => {
			throw error;
		});

		const pending = bridge.request("echo", { bad: BigInt(1) });

		await expect(pending).rejects.toBe(error);
		bridge.dispose(new PulseChannelResetError("closed"));
		expect(reject).toHaveBeenCalledTimes(1);
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
		const { bridge, client } = makeClient();
		const rejectWhere = vi.spyOn(client.replies, "rejectWhere");
		const pending = bridge.request("close-me");
		bridge.handleServerMessage({
			type: "channel_message",
			channel: "chan-1",
			event: "__close__",
		});
		await expect(pending).rejects.toBeInstanceOf(PulseChannelResetError);
		bridge.dispose(new PulseChannelResetError("closed again"));
		expect(rejectWhere).toHaveBeenCalledTimes(1);
	});

	it("does not reject settled requests when closed", async () => {
		const { bridge, client, sent } = makeClient();
		const pending = bridge.request("settled");
		const request = sent[0];
		const requestId = request && "requestId" in request ? request.requestId : undefined;
		client.replies.apply({
			type: "reply",
			id: requestId!,
			payload: "done",
		});
		await expect(pending).resolves.toBe("done");

		bridge.dispose(new PulseChannelResetError("closed"));
		await expect(pending).resolves.toBe("done");
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
