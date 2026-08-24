import { afterEach, describe, expect, it, vi } from "bun:test";
import { render } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router";
import { ChannelBridge, PulseChannelResetError, usePulseChannel } from "./channel";
import { PulseSocketIOClient } from "./client";
import type { ChannelRequestMessage, ClientChannelMessage } from "./messages";
import { PulseProvider, PulseView } from "./pulse";

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
		const requestId = (sent[0] as ChannelRequestMessage).requestId;
		expect(sent[0]).toMatchObject({
			type: "channel",
			action: "request",
			channel: "chan-1",
			event: "echo",
			payload: { foo: 1 },
		});
		bridge.handleServerMessage({
			type: "channel",
			action: "response",
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
			type: "channel",
			action: "event",
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
			type: "channel",
			action: "request",
			channel: "chan-1",
			event: "compute",
			requestId: "req-1",
			payload: {},
		});
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(sendMessage).toHaveBeenCalledWith(
			expect.objectContaining({
				type: "channel",
				action: "response",
				responseTo: "req-1",
				payload: 99,
			}),
		);
	});

	it("rejects pending requests when disposed", async () => {
		const { bridge } = makeClient();
		const pending = bridge.request("close-me");
		bridge.dispose(new PulseChannelResetError("Channel closed by server"));
		await expect(pending).rejects.toBeInstanceOf(PulseChannelResetError);
	});

	it("rejects pending requests on transport disconnect without closing", async () => {
		const { bridge, sent } = makeClient();
		const pending = bridge.request("during-disconnect");

		bridge.handleDisconnect(new PulseChannelResetError("Connection lost"));

		await expect(pending).rejects.toThrow("Connection lost");
		expect(bridge.closed).toBe(false);
		expect(() => bridge.on("event", vi.fn())).not.toThrow();
		bridge.emit("after-reconnect");
		expect(sent.at(-1)).toMatchObject({ event: "after-reconnect" });
	});

	it("does not close the bridge on release and reuses it on reacquire", () => {
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
		client.releaseChannel("chan-1", first);

		expect(first.closed).toBe(false);
		expect(() => first.on("event", vi.fn())).not.toThrow();

		const second = client.acquireChannel("chan-1");
		expect(second).toBe(first);
		expect(() => second.emit("after-release")).not.toThrow();
	});

	it("no-ops emit after the server closes the bridge", () => {
		const { bridge, sent } = makeClient();
		bridge.dispose(new PulseChannelResetError("Channel closed by server"));
		expect(() => bridge.emit("after-close")).not.toThrow();
		expect(sent).toHaveLength(0);
	});
});

describe("usePulseChannel", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("returns a bridge on the first render and subscribes with the matching owner", () => {
		const path = "/current-route";
		const fakeClient = { sendMessage: vi.fn() } as any;
		vi.spyOn(PulseSocketIOClient.prototype, "connect").mockResolvedValue();
		const ensureChannel = vi
			.spyOn(PulseSocketIOClient.prototype, "ensureChannel")
			.mockImplementation((id) => new ChannelBridge(fakeClient, id));
		const subscribeChannel = vi
			.spyOn(PulseSocketIOClient.prototype, "subscribeChannel")
			.mockImplementation(() => {});
		const unsubscribeChannel = vi
			.spyOn(PulseSocketIOClient.prototype, "unsubscribeChannel")
			.mockImplementation(() => {});

		const firstRender: Array<ChannelBridge | null> = [];

		function Probe({
			channelId,
			lifetime,
		}: {
			channelId: string;
			lifetime: "route" | "tab";
		}) {
			const bridge = usePulseChannel(channelId, lifetime);
			firstRender.push(bridge);
			return null;
		}

		const view = render(
			React.createElement(
				MemoryRouter,
				null,
				React.createElement(
					PulseProvider,
					{
						children: React.createElement(PulseView, { path, registry: { Probe } }),
						config: {
							serverAddress: "http://pulse.test",
							apiPrefix: "/_pulse",
							connectionStatus: {
								initialConnectingDelay: 0,
								initialErrorDelay: 0,
								reconnectErrorDelay: 0,
							},
						},
						prerender: {
							directives: {},
							views: {
								[path]: {
									vdom: {
										tag: "div",
										children: [
											{
												tag: "$$Probe",
												props: { channelId: "route-channel", lifetime: "route" },
											},
											{
												tag: "$$Probe",
												props: { channelId: "tab-channel", lifetime: "tab" },
											},
										],
									},
								},
							},
						},
					},
				),
			),
			{ reactStrictMode: true },
		);

		expect(firstRender.length).toBeGreaterThan(0);
		expect(firstRender.every((bridge) => bridge instanceof ChannelBridge)).toBe(true);

		expect([...new Set(ensureChannel.mock.calls.map(([id]) => id))].sort()).toEqual([
			"route-channel",
			"tab-channel",
		]);
		expect(
			subscribeChannel.mock.calls.some(
				([bridge, ownership]) =>
					bridge.id === "route-channel" &&
					ownership?.token === path &&
					ownership?.attachPath === path,
			),
		).toBe(true);
		expect(
			subscribeChannel.mock.calls.some(
				([bridge, ownership]) => bridge.id === "tab-channel" && ownership === undefined,
			),
		).toBe(true);

		view.unmount();

		expect(
			unsubscribeChannel.mock.calls.some(([bridge]) => bridge.id === "route-channel"),
		).toBe(true);
		expect(
			unsubscribeChannel.mock.calls.some(([bridge]) => bridge.id === "tab-channel"),
		).toBe(true);
	});
});
