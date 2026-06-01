import { beforeEach, describe, expect, it, mock, vi } from "bun:test";
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

function makeView(pathRouteInfo = routeInfo) {
	return {
		routeInfo: pathRouteInfo,
		onInit: vi.fn(),
		onUpdate: vi.fn(),
		onJsExec: vi.fn(),
		onServerError: vi.fn(),
	};
}

async function makeClient() {
	const { PulseSocketIOClient } = await import("./client");
	return new PulseSocketIOClient("http://pulse.test", {}, vi.fn() as any, {
		initialConnectingDelay: 0,
		initialErrorDelay: 0,
		reconnectErrorDelay: 0,
	});
}

function sentMessages() {
	return socket.emitted
		.filter(([event]) => event === "message")
		.map(([, payload]) =>
			deserialize(payload as any, { coerceNullsToUndefined: true }),
		);
}

describe("PulseSocketIOClient attach ack", () => {
	beforeEach(() => {
		io.mockClear();
	});

	it("queues callbacks until the active attach is acknowledged", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", makeView());
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
		client.attach("/", makeView());
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
			{
				type: "client_resume",
				resumeId: expect.any(String),
				views: [],
				channels: [{ channel: "chan-1", path: "/view" }],
			},
		]);
		const resume = sentMessages()[0]!;
		socket.trigger(
			"message",
			serialize({
				type: "server_resume",
				resumeId: resume.resumeId,
				status: "ok",
				views: [],
				channels: [{ channel: "chan-1", path: "/view" }],
			}),
		);
		expect(() => bridge.emit("after-reconnect")).not.toThrow();
	});

	it("does not replay stale channel disconnect after offline release and reacquire", async () => {
		const client = await makeClient();
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		client.acquireChannel("chan-1", "/view");
		socket.trigger("disconnect");
		client.releaseChannel("chan-1", "/view");
		client.acquireChannel("chan-1", "/view");

		socket.emitted = [];
		socket.trigger("connect");

		expect(sentMessages()).toEqual([
			{
				type: "client_resume",
				resumeId: expect.any(String),
				views: [],
				channels: [{ channel: "chan-1", path: "/view" }],
			},
		]);
		const resume = sentMessages()[0]!;
		socket.trigger(
			"message",
			serialize({
				type: "server_resume",
				resumeId: resume.resumeId,
				status: "ok",
				views: [],
				channels: [{ channel: "chan-1", path: "/view" }],
			}),
		);

		expect(sentMessages()).toEqual([
			{
				type: "client_resume",
				resumeId: resume.resumeId,
				views: [],
				channels: [{ channel: "chan-1", path: "/view" }],
			},
		]);
	});

	it("keeps queued callbacks behind resume acceptance", async () => {
		const client = await makeClient();
		const connected = client.connect();
		client.attach("/", makeView());
		socket.trigger("connect");
		await connected;

		const attach = sentMessages()[0]!;
		socket.trigger(
			"message",
			serialize({
				type: "attach_ack",
				path: "/",
				attachId: attach.attachId,
			}),
		);

		socket.trigger("disconnect");
		client.invokeCallback("/", "1.onClick", []);
		socket.emitted = [];
		socket.trigger("connect");

		expect(sentMessages()).toEqual([
			{
				type: "client_resume",
				resumeId: expect.any(String),
				views: [{ path: "/", routeInfo, attachId: attach.attachId }],
				channels: [],
			},
		]);

		const resume = sentMessages()[0]!;
		socket.trigger(
			"message",
			serialize({
				type: "server_resume",
				resumeId: resume.resumeId,
				status: "ok",
				views: [{ path: "/", attachId: attach.attachId }],
				channels: [],
			}),
		);

		expect(sentMessages()[1]).toMatchObject({
			type: "callback",
			path: "/",
			callback: "1.onClick",
		});
	});

	it("drops queued channel messages and closes bridge when channel is not resumed", async () => {
		const client = await makeClient();
		const connected = client.connect();
		socket.trigger("connect");
		await connected;

		const bridge = client.acquireChannel("chan-1", "/view");
		socket.trigger("disconnect");
		bridge.emit("offline-event");
		socket.emitted = [];
		socket.trigger("connect");

		const resume = sentMessages()[0]!;
		socket.trigger(
			"message",
			serialize({
				type: "server_resume",
				resumeId: resume.resumeId,
				status: "ok",
				views: [],
				channels: [],
			}),
		);

		expect(sentMessages()).toEqual([
			{
				type: "client_resume",
				resumeId: resume.resumeId,
				views: [],
				channels: [{ channel: "chan-1", path: "/view" }],
			},
		]);
		expect(() => bridge.emit("after-refusal")).toThrow("Channel is closed");
	});
});
