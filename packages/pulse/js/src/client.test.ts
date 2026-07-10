import { beforeEach, describe, expect, it, mock, vi } from "bun:test";
import React from "react";
import { act, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ViewSnapshot } from "./messages";
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

const snapshot = {
	viewId: "view-1",
	revision: 0,
	vdom: "initial",
};

const view = {
	routeInfo,
	onInit: vi.fn(),
	onUpdate: vi.fn(),
	onJsExec: vi.fn(),
	onServerError: vi.fn(),
};

async function makeClient(
	connectionStatus: {
		initialConnectingDelay: number;
		initialErrorDelay: number;
		reconnectErrorDelay: number;
	} = {
		initialConnectingDelay: 0,
		initialErrorDelay: 0,
		reconnectErrorDelay: 0,
	},
	frameworkNavigate = vi.fn() as any,
) {
	const { PulseSocketIOClient } = await import("./client");
	return new PulseSocketIOClient(
		"http://pulse.test",
		{},
		frameworkNavigate,
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

function receive(message: Record<string, unknown>, target: FakeSocket = socket) {
	target.trigger("message", serialize(message));
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
		client.attach("/", snapshot, view);
		socket.trigger("connect");
		await connected;

		const attach = sentMessages()[0]!;
		expect(attach).toMatchObject({
			type: "attach",
			path: "/",
			viewId: "view-1",
			revision: 0,
		});

		client.invokeCallback("/", "1.onClick", []);
		expect(sentMessages()).toHaveLength(1);

		socket.trigger(
			"message",
			serialize({
				type: "attach_ack",
				path: "/",
				attachId: attach.attachId,
				viewId: snapshot.viewId,
				revision: snapshot.revision,
			}),
		);

		expect(sentMessages()[1]).toMatchObject({
			type: "callback",
			path: "/",
			viewId: "view-1",
			callback: "1.onClick",
		});
	});

	it("applies contiguous updates and drops duplicates", async () => {
		const onUpdate = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onUpdate });
		socket.trigger("connect");
		await connected;

		receive({
			type: "vdom_update",
			path: "/",
			viewId: "view-1",
			baseRevision: 0,
			revision: 1,
			ops: [],
		});
		receive({
			type: "vdom_update",
			path: "/",
			viewId: "view-1",
			baseRevision: 0,
			revision: 1,
			ops: [],
		});
		receive({
			type: "vdom_update",
			path: "/",
			viewId: "stale-view",
			baseRevision: 1,
			revision: 2,
			ops: [],
		});

		expect(onUpdate).toHaveBeenCalledTimes(1);
		expect(sentMessages().filter((message) => message.type === "attach")).toHaveLength(1);
		client.updateRoute("/", routeInfo);
		expect(sentMessages().at(-1)).toMatchObject({
			type: "update",
			viewId: "view-1",
			revision: 1,
		});
	});

	it("requests one reattach when an update has a revision gap", async () => {
		const onUpdate = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onUpdate });
		socket.trigger("connect");
		await connected;
		const firstAttach = sentMessages()[0]!;
		receive({
			type: "attach_ack",
			path: "/",
			attachId: firstAttach.attachId,
			viewId: "view-1",
			revision: 0,
		});

		const gap = {
			type: "vdom_update",
			path: "/",
			viewId: "view-1",
			baseRevision: 1,
			revision: 2,
			ops: [],
		};
		receive(gap);
		receive(gap);

		expect(onUpdate).not.toHaveBeenCalled();
		expect(sentMessages().filter((message) => message.type === "attach")).toHaveLength(2);
		expect(sentMessages().at(-1)).toMatchObject({
			type: "attach",
			viewId: "view-1",
			revision: 0,
		});
	});

	it("installs an attach snapshot atomically and drops old-view callbacks", async () => {
		const onInit = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onInit });
		socket.trigger("connect");
		await connected;
		const attach = sentMessages()[0]!;

		client.invokeCallback("/", "old.onClick", []);
		receive({
			type: "attach_ack",
			path: "/",
			attachId: attach.attachId,
			viewId: "view-2",
			revision: 4,
			snapshot: { viewId: "view-2", revision: 4, vdom: "recovered" },
		});

		expect(onInit).toHaveBeenCalledWith({
			viewId: "view-2",
			revision: 4,
			vdom: "recovered",
		});
		expect(sentMessages().map((message) => message.type)).toEqual(["attach"]);

		client.invokeCallback("/", "new.onClick", []);
		expect(sentMessages().at(-1)).toMatchObject({
			type: "callback",
			viewId: "view-2",
			callback: "new.onClick",
		});
	});

	it("ignores stale acknowledgements from an older attach", async () => {
		const onInit = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onInit });
		socket.trigger("connect");
		await connected;
		const attach = sentMessages()[0]!;

		receive({
			type: "attach_ack",
			path: "/",
			attachId: `${attach.attachId}-stale`,
			viewId: "view-2",
			revision: 1,
			snapshot: { viewId: "view-2", revision: 1, vdom: "stale" },
		});

		expect(onInit).not.toHaveBeenCalled();
		client.invokeCallback("/", "1.onClick", []);
		expect(sentMessages()).toHaveLength(1);
	});

	it("treats the active attach snapshot as authoritative", async () => {
		const onInit = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onInit });
		socket.trigger("connect");
		await connected;
		const attach = sentMessages()[0]!;
		receive({
			type: "vdom_update",
			path: "/",
			viewId: "view-1",
			baseRevision: 0,
			revision: 1,
			ops: [],
		});

		receive({
			type: "attach_ack",
			path: "/",
			attachId: attach.attachId,
			viewId: "view-1",
			revision: 0,
			snapshot: { viewId: "view-1", revision: 0, vdom: "authoritative" },
		});

		expect(onInit).toHaveBeenCalledWith({
			viewId: "view-1",
			revision: 0,
			vdom: "authoritative",
		});
		client.updateRoute("/", routeInfo);
		expect(sentMessages().at(-1)).toMatchObject({ type: "update", revision: 0 });
	});

	it("installs a same-path loader snapshot before sending route metadata", async () => {
		const onInit = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onInit });
		socket.trigger("connect");
		await connected;

		client.installSnapshot("/", { viewId: "view-2", revision: 3, vdom: "loader" });
		client.installSnapshot("/", { viewId: "view-2", revision: 2, vdom: "stale" });
		client.updateRoute("/", routeInfo);

		expect(onInit).toHaveBeenCalledWith({
			viewId: "view-2",
			revision: 3,
			vdom: "loader",
		});
		expect(sentMessages().at(-1)).toMatchObject({
			type: "update",
			viewId: "view-2",
			revision: 3,
		});
		expect(onInit).toHaveBeenCalledTimes(1);
	});

	it("fences errors and navigation from stale views", async () => {
		const frameworkNavigate = vi.fn();
		const onServerError = vi.fn();
		const client = await makeClient(undefined, frameworkNavigate);
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onServerError });
		socket.trigger("connect");
		await connected;
		const error = { message: "failed", phase: "render" };

		receive({ type: "server_error", path: "/", viewId: "stale-view", error });
		receive({ type: "server_error", path: "/", viewId: "view-1", error });
		receive({
			type: "navigate_to",
			path: "/stale",
			replace: false,
			hard: false,
			origin: { viewId: "stale-view", pathname: "/" },
		});
		receive({
			type: "navigate_to",
			path: "/current",
			replace: false,
			hard: false,
			origin: { viewId: "view-1", pathname: "/" },
		});

		expect(onServerError).toHaveBeenCalledTimes(1);
		expect(frameworkNavigate).toHaveBeenCalledTimes(1);
		expect(frameworkNavigate).toHaveBeenCalledWith("/current", { replace: false });
	});

	it("reattaches only for a resync request targeting the active view", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, view);
		socket.trigger("connect");
		await connected;
		const attach = sentMessages()[0]!;
		receive({
			type: "attach_ack",
			path: "/",
			attachId: attach.attachId,
			viewId: "view-1",
			revision: 0,
		});

		receive({ type: "resync_view", path: "/", viewId: "stale-view" });
		receive({ type: "resync_view", path: "/", viewId: "view-1" });
		receive({ type: "resync_view", path: "/", viewId: "view-1" });

		expect(sentMessages().filter((message) => message.type === "attach")).toHaveLength(2);
	});

	it("returns an error for JavaScript execution from a stale view", async () => {
		const onJsExec = vi.fn();
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, { ...view, onJsExec });
		socket.trigger("connect");
		await connected;

		receive({
			type: "js_exec",
			path: "/",
			viewId: "stale-view",
			id: "js-1",
			expr: null,
		});

		expect(onJsExec).not.toHaveBeenCalled();
		expect(sentMessages().at(-1)).toMatchObject({
			type: "js_result",
			viewId: "stale-view",
			id: "js-1",
			error: "View is no longer active",
		});
	});

	it("drops queued callbacks when the path detaches before ack", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, view);
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
				viewId: snapshot.viewId,
				revision: snapshot.revision,
			}),
		);

		expect(sentMessages().map((message) => message.type)).toEqual([
			"attach",
			"detach",
		]);
		expect(sentMessages()[1]).toMatchObject({ type: "detach", viewId: "view-1" });
	});

	it("suspends hidden tabs without clearing active views and reattaches on resume", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", snapshot, view);
		const firstSocket = socket;
		firstSocket.trigger("connect");
		await connected;
		receive(
			{
				type: "vdom_update",
				path: "/",
				viewId: "view-1",
				baseRevision: 0,
				revision: 1,
				ops: [],
			},
			firstSocket,
		);

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
			viewId: "view-1",
			revision: 1,
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

	it("installs new prerender data for a PulseView that stays mounted", async () => {
		const { PulseProvider, PulseView } = await import("./pulse");
		const config = {
			serverAddress: "http://pulse.test",
			apiPrefix: "/_pulse",
			connectionStatus: {
				initialConnectingDelay: 0,
				initialErrorDelay: 0,
				reconnectErrorDelay: 0,
			},
		};
		const app = (viewSnapshot: ViewSnapshot) =>
			React.createElement(
				MemoryRouter,
				null,
				React.createElement(
					PulseProvider,
					{
						config,
						prerender: { views: { "/": viewSnapshot }, directives: {} },
						children: React.createElement(PulseView, { path: "/", registry: {} }),
					},
				),
			);
		const mounted = render(
			app({
				viewId: "view-1",
				revision: 0,
				vdom: { tag: "div", children: ["first"] },
			}),
		);

		expect(mounted.container.textContent).toBe("first");
		mounted.rerender(
			app({
				viewId: "view-1",
				revision: 1,
				vdom: { tag: "div", children: ["second"] },
			}),
		);

		expect(mounted.container.textContent).toBe("second");
		mounted.unmount();
	});
});
