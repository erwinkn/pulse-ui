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
		client.releaseChannel("chan-1", first);

		expect(() => first.on("event", vi.fn())).toThrow(PulseChannelResetError);

		const second = client.acquireChannel("chan-1");
		expect(second).not.toBe(first);
		expect(() => second.on("event", vi.fn())).not.toThrow();
	});
});

describe("usePulseChannel", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("uses route ownership only for route-lifetime channels and releases each exact bridge", () => {
		const path = "/current-route";
		const fakeClient = { sendMessage: vi.fn() } as any;
		const acquiredBridges: ChannelBridge[] = [];
		vi.spyOn(PulseSocketIOClient.prototype, "connect").mockResolvedValue();
		const acquireChannel = vi
			.spyOn(PulseSocketIOClient.prototype, "acquireChannel")
			.mockImplementation((id) => {
				const bridge = new ChannelBridge(fakeClient, id);
				acquiredBridges.push(bridge);
				return bridge;
			});
		const releaseChannel = vi
			.spyOn(PulseSocketIOClient.prototype, "releaseChannel")
			.mockImplementation(() => {});

		function Probe({
			channelId,
			lifetime,
		}: {
			channelId: string;
			lifetime: "route" | "tab";
		}) {
			usePulseChannel(channelId, lifetime);
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

		expect(acquireChannel.mock.calls).toEqual([
			["route-channel", { token: path, attachPath: path }],
			["tab-channel", undefined],
			["route-channel", { token: path, attachPath: path }],
			["tab-channel", undefined],
		]);

		view.unmount();

		expect(releaseChannel.mock.calls).toEqual([
			["route-channel", acquiredBridges[0]],
			["tab-channel", acquiredBridges[1]],
			["route-channel", acquiredBridges[2]],
			["tab-channel", acquiredBridges[3]],
		]);
	});
});
