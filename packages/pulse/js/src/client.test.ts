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
const io = vi.fn((_url?: string, _options?: Record<string, any>) => {
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
	directives: Record<string, any> = {},
) {
	const { PulseSocketIOClient } = await import("./client");
	return new PulseSocketIOClient(
		"http://pulse.test",
		directives,
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

	it("keeps one page identity across reconnects and client remounts", async () => {
		const client = await makeClient(undefined, {
			socketio: { auth: { tenant: "stoneware" } },
		});
		const connected = client.connect();
		const firstOptions = io.mock.calls.at(-1)?.[1];
		socket.trigger("connect");
		await connected;

		client.suspend();
		const resumed = client.resume();
		const secondOptions = io.mock.calls.at(-1)?.[1];
		socket.trigger("connect");
		await resumed;

		const remountedClient = await makeClient();
		const remounted = remountedClient.connect();
		const remountedOptions = io.mock.calls.at(-1)?.[1];
		socket.trigger("connect");
		await remounted;

		const firstAuth = firstOptions?.auth as Record<string, string>;
		expect(firstAuth.tenant).toBe("stoneware");
		expect(firstAuth.__pulse_page_instance_id).toBeTruthy();
		expect(secondOptions?.auth.__pulse_page_instance_id).toBe(
			firstAuth.__pulse_page_instance_id,
		);
		expect(remountedOptions?.auth.__pulse_page_instance_id).toBe(
			firstAuth.__pulse_page_instance_id,
		);
	});

	it("reloads only the page rejected for a render ID collision", async () => {
		const reload = vi.fn();
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
		Object.defineProperty(window.location, "reload", {
			configurable: true,
			value: reload,
		});
		const client = await makeClient();
		const connected = client.connect();
		const error = Object.assign(new Error("collision"), {
			data: { code: "render_id_collision" },
		});

		socket.trigger("connect_error", error);
		await expect(connected).rejects.toBe(error);

		expect(reload).toHaveBeenCalledTimes(1);
		consoleError.mockRestore();
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

	it("applies current HTTP directives to api_call fetches", async () => {
		const fetchMock = vi.fn(
			async (_input: RequestInfo | URL, _init?: RequestInit) =>
				new Response(JSON.stringify({ ok: true }), {
					status: 200,
					headers: { "content-type": "application/json" },
				}),
		);
		globalThis.fetch = fetchMock as any;
		const client = await makeClient();
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		client.setDirectives({
			query: {
				pulse_deployment: "prod-new",
			},
			headers: {
				"x-router-affinity": "prod-new",
			},
		});
		socket.trigger(
			"message",
			serialize({
				type: "api_call",
				id: "call-1",
				url: "http://pulse.test/api/users?existing=1&pulse_deployment=prod-old",
				method: "POST",
				headers: {
					"x-call-header": "client",
				},
				body: { ok: true },
				credentials: "omit",
			}),
		);
		await waitForEffects();

		const call = fetchMock.mock.calls[0];
		expect(call).toBeDefined();
		const [url, init] = call as [URL, RequestInit];
		expect(url).toEqual(
			new URL(
				"http://pulse.test/api/users?existing=1&pulse_deployment=prod-new",
				window.location.href,
			),
		);
		const headers = new Headers(init.headers);
		expect(headers.get("x-router-affinity")).toBe("prod-new");
		expect(headers.get("x-call-header")).toBe("client");
		expect(headers.get("content-type")).toBe("application/json");
		expect(init.credentials).toBe("omit");

		expect(sentMessages().at(-1)).toEqual({
			type: "api_result",
			id: "call-1",
			ok: true,
			status: 200,
			headers: {
				"content-type": "application/json",
			},
			body: { ok: true },
		});
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
