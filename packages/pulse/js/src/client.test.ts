import { beforeEach, describe, expect, it, mock, vi } from "bun:test";
import React from "react";
import { act, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { deserialize, serialize } from "./serialize/serializer";

class FakeSocket {
	connected = false;
	emitted: [string, unknown][] = [];
	#handlers = new Map<string, (...args: any[]) => void>();

	on(event: string, handler: (...args: any[]) => void): this {
		this.#handlers.set(event, handler);
		return this;
	}

	emit(event: string, payload: unknown): this {
		this.emitted.push([event, payload]);
		return this;
	}

	trigger(event: string, ...args: any[]): void {
		if (event === "connect") this.connected = true;
		if (event === "disconnect") this.connected = false;
		this.#handlers.get(event)?.(...args);
	}

	disconnect(): void {
		this.trigger("disconnect");
	}
}

let socket: FakeSocket;
const io = vi.fn(() => {
	socket = new FakeSocket();
	return socket;
});

mock.module("socket.io-client", () => ({ io }));

const routeInfo = {
	hash: "",
	pathname: "/",
	query: "",
	queryParams: {},
	pathParams: {},
	catchall: [],
};

const view = {
	routeInfo,
	onInit: vi.fn(),
	onUpdate: vi.fn(),
	onJsExec: vi.fn(),
	onServerError: vi.fn(),
};

async function makeClient(
	connectionStatus = {
		initialConnectingDelay: 0,
		initialErrorDelay: 0,
		reconnectErrorDelay: 0,
	},
) {
	const { PulseSocketIOClient } = await import("./client");
	return new PulseSocketIOClient(
		"http://pulse.test",
		{},
		vi.fn() as any,
		connectionStatus,
	);
}

function sentMessages(target: FakeSocket = socket) {
	return target.emitted
		.filter(([event]) => event === "message")
		.map(([, payload]) =>
			deserialize(payload as any, { coerceNullsToUndefined: true }),
		);
}

function waitForEffects() {
	return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("PulseSocketIOClient attach ack", () => {
	beforeEach(() => {
		io.mockClear();
		Object.defineProperty(document, "visibilityState", {
			configurable: true,
			value: "visible",
		});
		Object.defineProperty(navigator, "onLine", {
			configurable: true,
			value: true,
		});
	});

	it("queues callbacks until the active attach is acknowledged", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", view);
		socket.trigger("connect");
		await connected;

		const attach = sentMessages()[0]!;
		expect(attach).toMatchObject({ type: "attach", path: "/" });

		client.invokeCallback("/", "1.onClick", []);
		expect(sentMessages()).toHaveLength(1);

		socket.trigger(
			"message",
			serialize({
				type: "attach_ack",
				path: "/",
				attachId: attach.attachId,
			}),
		);

		expect(sentMessages()[1]).toMatchObject({
			type: "callback",
			path: "/",
			callback: "1.onClick",
		});
	});

	it("drops queued callbacks when the path detaches before ack", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", view);
		socket.trigger("connect");
		await connected;

		const attach = sentMessages()[0]!;
		client.invokeCallback("/", "1.onClick", []);
		client.detach("/");
		socket.trigger(
			"message",
			serialize({
				type: "attach_ack",
				path: "/",
				attachId: attach.attachId,
			}),
		);

		expect(sentMessages().map((message) => message.type)).toEqual([
			"attach",
			"detach",
		]);
	});

	it("coalesces queued channel lifecycle messages on initial connect", async () => {
		const client = await makeClient();
		const connected = client.connect();

		client.acquireChannel("chan-1", "/view");
		client.releaseChannel("chan-1", "/view");
		client.acquireChannel("chan-1", "/view");

		socket.trigger("connect");
		await connected;

		expect(sentMessages()).toEqual([
			{ type: "channel_connect", channel: "chan-1", path: "/view" },
		]);
	});

	it("rejects channel requests on transport disconnect and reconnects endpoint", async () => {
		const client = await makeClient();
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		const bridge = client.acquireChannel("chan-1", "/view");
		const pending = bridge.request("needs-response");

		socket.trigger("disconnect");
		await expect(pending).rejects.toThrow("Connection lost");

		socket.emitted = [];
		socket.trigger("connect");

		expect(sentMessages()).toEqual([
			{ type: "channel_connect", channel: "chan-1", path: "/view" },
		]);
		expect(() => bridge.emit("after-reconnect")).not.toThrow();
	});

	it("suspends hidden tabs without clearing active views and reattaches on resume", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", view);
		const firstSocket = socket;
		firstSocket.trigger("connect");
		await connected;

		client.suspend();

		expect(client.isConnected()).toBe(false);
		expect(firstSocket.connected).toBe(false);
		expect(sentMessages(firstSocket).map((message) => message.type)).toEqual([
			"attach",
		]);

		const resumed = client.resume();
		const secondSocket = socket;
		expect(secondSocket).not.toBe(firstSocket);
		secondSocket.trigger("connect");
		await resumed;

		expect(sentMessages(secondSocket)[0]).toMatchObject({
			type: "attach",
			path: "/",
		});
	});

	it("does not reload visible active tabs when reconnect times out", async () => {
		const reload = vi.fn();
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const client = await makeClient();
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		socket.trigger("disconnect");
		await waitForEffects();

		expect(reload).not.toHaveBeenCalled();
	});

	it("reloads when resume from suspension cannot reconnect", async () => {
		const reload = vi.fn();
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const client = await makeClient({
			initialConnectingDelay: 0,
			initialErrorDelay: 0,
			reconnectErrorDelay: 20,
		});
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		client.suspend();
		void client.resume().catch(() => {});
		socket.trigger("connect_error", new Error("websocket error"));
		await new Promise((resolve) => setTimeout(resolve, 25));

		expect(reload).toHaveBeenCalled();
		consoleError.mockRestore();
	});

	it("does not postpone resume reload on repeated reconnect errors", async () => {
		const reload = vi.fn();
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const client = await makeClient({
			initialConnectingDelay: 0,
			initialErrorDelay: 0,
			reconnectErrorDelay: 20,
		});
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		client.suspend();
		void client.resume().catch(() => {});
		await new Promise((resolve) => setTimeout(resolve, 15));
		socket.trigger("connect_error", new Error("websocket error"));
		await new Promise((resolve) => setTimeout(resolve, 10));

		expect(reload).toHaveBeenCalled();
		consoleError.mockRestore();
	});

	it("does not reconnect or reload while suspended", async () => {
		const reload = vi.fn();
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const client = await makeClient({
			initialConnectingDelay: 0,
			initialErrorDelay: 0,
			reconnectErrorDelay: 0,
		});
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		client.suspend();
		await waitForEffects();

		expect(io).toHaveBeenCalledTimes(1);
		expect(reload).not.toHaveBeenCalled();
	});

	it("does not reload hidden tabs when reconnect times out", async () => {
		const reload = vi.fn();
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		Object.defineProperty(document, "visibilityState", {
			configurable: true,
			value: "hidden",
		});
		const client = await makeClient();
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		socket.trigger("disconnect");
		await waitForEffects();

		expect(reload).not.toHaveBeenCalled();
	});
});

describe("PulseProvider connection handling", () => {
	beforeEach(() => {
		io.mockClear();
		Object.defineProperty(document, "visibilityState", {
			configurable: true,
			value: "visible",
		});
	});

	it("handles initial connection errors without an unhandled rejection", async () => {
		const { PulseProvider } = await import("./pulse");
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

		render(
			React.createElement(
				MemoryRouter,
				null,
				React.createElement(
					PulseProvider,
					{
						config: {
							serverAddress: "http://pulse.test",
							apiPrefix: "/_pulse",
							connectionStatus: {
								initialConnectingDelay: 0,
								initialErrorDelay: 0,
								reconnectErrorDelay: 0,
							},
						},
						prerender: { views: {}, directives: {} },
						children: React.createElement("div", null, "child"),
					},
				),
			),
		);
		await waitForEffects();

		await act(async () => {
			socket.trigger("connect_error", new Error("websocket error"));
			await waitForEffects();
		});

		expect(io).toHaveBeenCalledTimes(1);
		consoleError.mockRestore();
	});
});
