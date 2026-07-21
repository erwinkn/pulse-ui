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
		const request = sent[0]!;
		if (request.type !== "channel_request") throw new Error("Expected channel request");
		const requestId = request.requestId;
		bridge.handleServerMessage({
			type: "channel_response",
			channel: "chan-1",
			responseTo: requestId,
			ok: true,
			payload: { foo: 2 },
		});
		await expect(pending).resolves.toEqual({ foo: 2 });
	});

	it("dispatches events to registered handlers", () => {
		const { bridge } = makeClient();
		const handler = vi.fn();
		bridge.on("ping", handler);
		bridge.handleServerMessage({
			type: "channel_event",
			channel: "chan-1",
			event: "ping",
			payload: { value: 42 },
		});
		expect(handler).toHaveBeenCalledWith({ value: 42 });
	});

	it("normalizes omitted payloads to null", async () => {
		const { bridge, sent } = makeClient();
		bridge.emit("omitted");
		bridge.emit("null", null);

		expect(sent.slice(0, 2)).toEqual([
			{ type: "channel_event", channel: "chan-1", event: "omitted", payload: null },
			{ type: "channel_event", channel: "chan-1", event: "null", payload: null },
		]);

		const omitted = bridge.request("request-omitted");
		const nullPayload = bridge.request("request-null", null);
		const omittedRequest = sent[2]!;
		const nullRequest = sent[3]!;
		if (omittedRequest.type !== "channel_request" || nullRequest.type !== "channel_request") {
			throw new Error("Expected channel requests");
		}
		bridge.handleServerMessage({
			type: "channel_response",
			channel: "chan-1",
			responseTo: omittedRequest.requestId,
			ok: true,
			payload: null,
		});
		bridge.handleServerMessage({
			type: "channel_response",
			channel: "chan-1",
			responseTo: nullRequest.requestId,
			ok: true,
			payload: null,
		});

		await expect(omitted).resolves.toBeNull();
		await expect(nullPayload).resolves.toBeNull();
	});

	it("responds to server requests", async () => {
		const { bridge, sendMessage } = makeClient();
		bridge.on("compute", () => 99);
		bridge.handleServerMessage({
			type: "channel_request",
			channel: "chan-1",
			event: "compute",
			requestId: "req-1",
			payload: {},
		});
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(sendMessage).toHaveBeenCalledWith({
			type: "channel_response",
			channel: "chan-1",
			responseTo: "req-1",
			ok: true,
			payload: 99,
		});
	});

	it("normalizes undefined response payloads to null", async () => {
		const { bridge, sendMessage } = makeClient();
		const first = vi.fn(() => undefined);
		bridge.on("notify", first);
		bridge.handleServerMessage({
			type: "channel_request",
			channel: "chan-1",
			event: "notify",
			requestId: "req-2",
			payload: null,
		});
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(sendMessage).toHaveBeenCalledWith({
			type: "channel_response",
			channel: "chan-1",
			responseTo: "req-2",
			ok: true,
			payload: null,
		});
		expect(first).toHaveBeenCalledWith(null);
	});

	it("sends a string error when a handler rejects with undefined", async () => {
		const { bridge, sendMessage } = makeClient();
		bridge.on("notify", () => Promise.reject());
		bridge.handleServerMessage({
			type: "channel_request",
			channel: "chan-1",
			event: "notify",
			requestId: "req-4",
			payload: null,
		});
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(sendMessage).toHaveBeenCalledWith({
			type: "channel_response",
			channel: "chan-1",
			responseTo: "req-4",
			ok: false,
			error: "undefined",
		});
	});

	it("uses the first non-undefined request handler response", async () => {
		const { bridge, sendMessage } = makeClient();
		const first = vi.fn(() => undefined);
		const second = vi.fn(() => "handled");
		bridge.on("notify", first);
		bridge.on("notify", second);
		bridge.handleServerMessage({
			type: "channel_request",
			channel: "chan-1",
			event: "notify",
			requestId: "req-3",
			payload: null,
		});
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(sendMessage).toHaveBeenCalledWith({
			type: "channel_response",
			channel: "chan-1",
			responseTo: "req-3",
			ok: true,
			payload: "handled",
		});
		expect(first).toHaveBeenCalledWith(null);
		expect(second).toHaveBeenCalledWith(null);
	});

	it("rejects pending requests when closed", async () => {
		const { bridge } = makeClient();
		const pending = bridge.request("close-me");
		bridge.handleServerMessage({
			type: "channel_event",
			channel: "chan-1",
			event: "__close__",
			payload: null,
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
