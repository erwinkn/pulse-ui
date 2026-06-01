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

const view = {
	routeInfo,
	onInit: vi.fn(),
	onUpdate: vi.fn(),
	onJsExec: vi.fn(),
	onServerError: vi.fn(),
	deserializeMessage: vi.fn((data) =>
		deserialize(data as any, { coerceNullsToUndefined: true }),
	),
};

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

	it("deserializes channel messages with the endpoint view deserializer", async () => {
		const client = await makeClient();
		const connected = client.connect();
		const viewA = {
			...view,
			deserializeMessage: vi.fn(() => ({
				type: "channel_message",
				channel: "chan-1",
				event: "ping",
				payload: { source: "a" },
			} as const)),
		};
		const viewB = {
			...view,
			deserializeMessage: vi.fn(() => {
				throw new Error("wrong view");
			}),
		};
		client.attach("/a", viewA);
		client.attach("/b", viewB);
		const bridge = client.acquireChannel("chan-1", "/a");
		const handler = vi.fn();
		bridge.on("ping", handler);
		socket.trigger("connect");
		await connected;

		socket.trigger(
			"message",
			serialize({
				type: "channel_message",
				channel: "chan-1",
				event: "ping",
				payload: { source: "wire" },
			}),
		);

		expect(viewA.deserializeMessage).toHaveBeenCalledTimes(1);
		expect(viewB.deserializeMessage).not.toHaveBeenCalled();
		expect(handler).toHaveBeenCalledWith({ source: "a" });
	});
});
