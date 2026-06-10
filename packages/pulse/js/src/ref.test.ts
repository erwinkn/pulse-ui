import { describe, expect, it, vi } from "bun:test";
import { RefRegistry } from "./ref";

type Handler = (payload: any) => any;

class FakeBridge {
	handlers = new Map<string, Set<Handler>>();
	emitted: Array<{ event: string; payload: any }> = [];

	on(event: string, handler: Handler): () => void {
		let bucket = this.handlers.get(event);
		if (!bucket) {
			bucket = new Set();
			this.handlers.set(event, bucket);
		}
		bucket.add(handler);
		return () => {
			const set = this.handlers.get(event);
			if (!set) return;
			set.delete(handler);
			if (set.size === 0) {
				this.handlers.delete(event);
			}
		};
	}

	emit(event: string, payload?: any): void {
		this.emitted.push({ event, payload });
	}

	trigger(event: string, payload: any): any {
		const handlers = this.handlers.get(event);
		let result: any;
		if (!handlers) return result;
		for (const handler of handlers) {
			result = handler(payload);
		}
		return result;
	}
}

function makeRegistry(bridge: FakeBridge, acquire = vi.fn(), release = vi.fn()) {
	return {
		registry: new RefRegistry({
			acquire: (channelId: string) => {
				acquire(channelId);
				return { bridge, release } as any;
			},
			dispose() {},
		}),
		acquire,
		release,
	};
}

describe("RefRegistry", () => {
	it("emits mount and unmount", () => {
		const bridge = new FakeBridge();
		const { registry } = makeRegistry(bridge);
		const cb = registry.getCallback("chan-1", "ref-1");

		cb({});
		cb(null);

		expect(bridge.emitted).toEqual([
			{ event: "ref:mounted", payload: { refId: "ref-1" } },
			{ event: "ref:unmounted", payload: { refId: "ref-1" } },
		]);
	});

	it("handles request ops", () => {
		const bridge = new FakeBridge();
		const { registry } = makeRegistry(bridge);
		const cb = registry.getCallback("chan-1", "ref-1");

		const element = {
			getAttribute: (name: string) => (name === "data-test" ? "ok" : null),
		};
		cb(element);

		const result = bridge.trigger("ref:request", {
			refId: "ref-1",
			op: "getAttr",
			payload: { name: "data-test" },
		});

		expect(result).toBe("ok");
	});

	it("handles call ops", () => {
		const bridge = new FakeBridge();
		const { registry } = makeRegistry(bridge);
		const cb = registry.getCallback("chan-1", "ref-1");

		const focus = vi.fn();
		cb({ focus });

		bridge.trigger("ref:call", {
			refId: "ref-1",
			op: "focus",
			payload: { preventScroll: true },
		});

		expect(focus).toHaveBeenCalled();
	});

	it("locks to a single channel until disposed", () => {
		const bridge = new FakeBridge();
		const { registry } = makeRegistry(bridge);
		registry.getCallback("chan-1", "ref-1")({});
		expect(() => registry.getCallback("chan-2", "ref-2")({})).toThrow(
			"[Pulse] Ref channel changed unexpectedly",
		);
		registry.dispose();
		expect(() => registry.getCallback("chan-2", "ref-2")({})).not.toThrow();
	});

	it("acquires lazily when the ref mounts and releases on dispose", () => {
		const bridge = new FakeBridge();
		const { registry, acquire, release } = makeRegistry(bridge);
		const cb = registry.getCallback("chan-1", "ref-1");

		expect(acquire).not.toHaveBeenCalled();
		cb({});
		expect(acquire).toHaveBeenCalledWith("chan-1");

		registry.dispose();
		expect(release).toHaveBeenCalledTimes(1);
	});
});
