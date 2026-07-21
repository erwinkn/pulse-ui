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

	it("resets after 10,000 unanswered requests", async () => {
		const { bridge, sent } = makeClient();
		const pending: Promise<any>[] = [];
		for (let index = 0; index < 10_000; index++) {
			pending.push(bridge.request("never-answers", index));
		}

		await expect(bridge.request("overflow")).rejects.toThrow("exceeded 10,000");
		expect(sent).toHaveLength(10_000);
		expect(bridge.isClosed).toBe(true);
		const settled = await Promise.allSettled(pending);
		expect(settled.every((result) => result.status === "rejected")).toBe(true);
	});

	it("resets after 10,000 events arrive without handlers", () => {
		const { bridge } = makeClient();
		for (let index = 0; index < 10_001; index++) {
			bridge.handleServerMessage({
				type: "channel_message",
				channel: "chan-1",
				event: "unhandled",
				payload: index,
			});
		}

		expect(bridge.isClosed).toBe(true);
		expect(() => bridge.on("unhandled", vi.fn())).toThrow("Channel is closed");
	});

	it("does not retain requests when sending throws", async () => {
		const { bridge, sendMessage } = makeClient();
		sendMessage.mockImplementationOnce(() => {
			throw new Error("send failed");
		});

		await expect(bridge.request("fails")).rejects.toThrow("send failed");
		expect(bridge.isClosed).toBe(false);
		const pending = bridge.request("works");
		expect(sendMessage).toHaveBeenCalledTimes(2);
		bridge.dispose(new PulseChannelResetError("done"));
		await expect(pending).rejects.toThrow("done");
	});

	it("bounds server requests whose handlers remain pending", () => {
		const { bridge } = makeClient();
		bridge.on("wait", () => new Promise(() => {}));
		for (let index = 0; index < 10_001; index++) {
			bridge.handleServerMessage({
				type: "channel_message",
				channel: "chan-1",
				event: "wait",
				requestId: String(index),
			});
		}

		expect(bridge.isClosed).toBe(true);
	});

	it("does not respond after closing during an in-flight server request", async () => {
		const { bridge, sendMessage } = makeClient();
		let resolve!: (value: string) => void;
		bridge.on("wait", () => new Promise<string>((done) => (resolve = done)));
		bridge.handleServerMessage({
			type: "channel_message",
			channel: "chan-1",
			event: "wait",
			requestId: "request-1",
		});

		bridge.dispose(new PulseChannelResetError("closed"));
		resolve("late");
		await new Promise((done) => setTimeout(done, 0));

		expect(sendMessage).not.toHaveBeenCalled();
	});
});
