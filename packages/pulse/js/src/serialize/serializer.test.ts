import { describe, expect, it } from "bun:test";
import { deserialize, serialize, type Serialized } from "./serializer";

function wireSerialize(data: unknown): Serialized {
	return JSON.parse(JSON.stringify(serialize(data)));
}

function wireRoundTrip(data: unknown): any {
	return deserialize(wireSerialize(data));
}

function semanticSnapshot(value: unknown, seen = new Map<object, number>()): unknown {
	if (
		value == null ||
		typeof value === "function" ||
		typeof value === "symbol" ||
		(typeof value === "number" && Number.isNaN(value))
	) {
		return null;
	}
	if (typeof value !== "object") {
		return value;
	}

	const previous = seen.get(value);
	if (previous !== undefined) {
		return ["ref", previous];
	}
	const id = seen.size;
	seen.set(value, id);

	if (value instanceof Date) {
		return ["date", id, value.toISOString()];
	}
	if (Array.isArray(value)) {
		return ["array", id, value.map((entry) => semanticSnapshot(entry, seen))];
	}
	if (value instanceof Set) {
		const entries = new Set<unknown>();
		for (const entry of value) {
			const snapshot = semanticSnapshot(entry);
			entries.add(snapshot === null ? null : entry);
		}
		return ["set", id, [...entries].map((entry) => semanticSnapshot(entry, seen))];
	}
	if (value instanceof Map) {
		const entries: Record<string, unknown> = Object.create(null);
		for (const [key, entry] of value) {
			entries[key] = entry;
		}
		return [
			"map",
			id,
			Object.keys(entries).map((key) => [key, semanticSnapshot(entries[key], seen)]),
		];
	}
	return [
		"object",
		id,
		Object.keys(value).map((key) => [
			key,
			semanticSnapshot((value as Record<string, unknown>)[key], seen),
		]),
	];
}

function seededRandom(seed: number): () => number {
	let state = seed;
	return () => {
		state |= 0;
		state = (state + 0x6d2b79f5) | 0;
		let value = Math.imul(state ^ (state >>> 15), 1 | state);
		value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
		return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
	};
}

function randomSerializable(
	random: () => number,
	depth: number,
	objects: object[] = [],
): unknown {
	const leaf = () => {
		switch (Math.floor(random() * 8)) {
			case 0:
				return null;
			case 1:
				return undefined;
			case 2:
				return random() < 0.5;
			case 3:
				return Math.floor(random() * 21) - 10;
			case 4:
				return random() < 0.5 ? "text" : "2024-01-01T00:00:00.000Z";
			case 5:
				return Number.NaN;
			case 6:
				return () => {};
			default:
				return Symbol("value");
		}
	};

	if (depth === 0) {
		return leaf();
	}

	const kind = Math.floor(random() * 7);
	if (kind === 0) {
		return leaf();
	}
	if (kind === 1) {
		const date = new Date(Date.UTC(2020 + Math.floor(random() * 10), 0, 1));
		objects.push(date);
		return date;
	}
	if (kind === 2 && objects.length > 0) {
		return objects[Math.floor(random() * objects.length)];
	}

	const size = Math.floor(random() * 4);
	if (kind === 3) {
		const value: unknown[] = [];
		objects.push(value);
		for (let i = 0; i < size; i++) {
			value.push(randomSerializable(random, depth - 1, objects));
		}
		return value;
	}
	if (kind === 4) {
		const value: Record<string, unknown> = Object.create(null);
		objects.push(value);
		for (let i = 0; i < size; i++) {
			const key = i === 0 && random() < 0.25 ? "__proto__" : String(Math.floor(random() * 5));
			value[key] = randomSerializable(random, depth - 1, objects);
		}
		return value;
	}
	if (kind === 5) {
		const value = new Set<unknown>();
		objects.push(value);
		for (let i = 0; i < size; i++) {
			if (random() < 0.25) {
				value.add(new Date(Date.UTC(2020 + Math.floor(random() * 10), 0, 1)));
			} else {
				value.add(randomSerializable(random, 0, objects));
			}
		}
		return value;
	}

	const value = new Map<string, unknown>();
	objects.push(value);
	for (let i = 0; i < size; i++) {
		const key = random() < 0.75 ? String(Math.floor(random() * 5)) : `key-${i}`;
		value.set(key, randomSerializable(random, depth - 1, objects));
	}
	return value;
}

describe("v4 serialization", () => {
	it("keeps metadata aligned when JSON drops undefined object values", () => {
		const data = {
			dropped: undefined,
			date: new Date("2024-01-01T00:00:00.000Z"),
		};

		const parsed = wireRoundTrip(data);

		expect(parsed).toEqual({ dropped: null, date: data.date });
		expect(parsed.date).toBeInstanceOf(Date);
	});

	it("keeps shared references aligned after undefined object values", () => {
		const shared = { value: 1 };
		const parsed = wireRoundTrip({
			dropped: undefined,
			first: shared,
			second: shared,
			tail: 2,
		});

		expect(parsed.dropped).toBeNull();
		expect(parsed.first).toBe(parsed.second);
		expect(parsed.first).toEqual(shared);
	});

	it("keeps Map values aligned when integer-like keys reorder", () => {
		const date = new Date("2024-01-01T00:00:00.000Z");
		const parsed = wireRoundTrip(
			new Map<string, unknown>([
				["2", date],
				["1", "2020-02-03T00:00:00.000Z"],
			]),
		);

		expect(parsed.get("2")).toEqual(date);
		expect(parsed.get("2")).toBeInstanceOf(Date);
		expect(parsed.get("1")).toBe("2020-02-03T00:00:00.000Z");
	});

	it("rejects non-string Map keys instead of merging them on the wire", () => {
		expect(() => serialize(new Map([[1, "value"]]))).toThrow(
			"Map keys must be strings, got 'number'",
		);
	});

	it("rejects Set objects that Python cannot materialize as set values", () => {
		expect(() => serialize(new Set([[1, 2]]))).toThrow(
			"Set values must be primitives or Dates",
		);
	});

	it("preserves own __proto__ keys without shifting metadata", () => {
		const data = JSON.parse('{"__proto__":0}') as Record<string, unknown>;
		data.date = new Date("2024-01-01T00:00:00.000Z");

		const parsed = wireRoundTrip(data);

		expect(Object.hasOwn(parsed, "__proto__")).toBeTrue();
		expect(parsed.__proto__).toBe(0);
		expect(parsed.date).toBeInstanceOf(Date);
	});

	it("canonicalizes Set values that collapse to null on the wire", () => {
		const data = {
			values: new Set([undefined, null, Number.NaN, () => {}, Symbol("value")]),
			date: new Date("2024-01-01T00:00:00.000Z"),
		};
		const wire = wireSerialize(data);
		const parsed = deserialize(wire) as typeof data;

		expect(parsed.values).toEqual(new Set([null]));
		expect(parsed.date).toBeInstanceOf(Date);
		expect(wireSerialize(parsed)).toEqual(wire);
	});

	it("decodes Python date literals with years below 100", () => {
		for (const year of [1, 50, 99, 100, 9999]) {
			const literal = `${String(year).padStart(4, "0")}-01-02`;
			const parsed = deserialize([[[], [0], [], []], literal]) as Date;
			expect(parsed.getUTCFullYear()).toBe(year);
			expect(parsed.getUTCMonth()).toBe(0);
			expect(parsed.getUTCDate()).toBe(2);
		}
	});

	it("rejects Dates outside Python's supported year range", () => {
		const yearZero = new Date(0);
		yearZero.setUTCFullYear(0);
		const yearTenThousand = new Date(0);
		yearTenThousand.setUTCFullYear(10_000);

		expect(() => serialize(yearZero)).toThrow("supported year range 0001-9999");
		expect(() => serialize(yearTenThousand)).toThrow("supported year range 0001-9999");
	});

	it("is stable across the JSON boundary for seeded random graphs", () => {
		for (let seed = 1; seed <= 1000; seed++) {
			const data = randomSerializable(seededRandom(seed), 4);
			const wire = wireSerialize(data);
			const parsed = deserialize(wire);
			const nextWire = wireSerialize(parsed);
			expect(semanticSnapshot(parsed)).toEqual(semanticSnapshot(data));
			if (JSON.stringify(nextWire) !== JSON.stringify(wire)) {
				throw new Error(
					`Wire round trip changed seeded case ${seed}: ${JSON.stringify(wire)} -> ${JSON.stringify(nextWire)}`,
				);
			}
		}
	});

	it("serializes primitives as direct entries and round trips", () => {
		const data = [1, "a", true, null, undefined];
		const ser = serialize(data);
		const parsed = deserialize(ser);
		expect(parsed).toEqual(data);
	});
	it("coerces nulls to undefined with the option", () => {
		const data = [1, null, undefined];
		const ser = serialize(data);
		const parsed = deserialize(ser, { coerceNullsToUndefined: true });
		expect(parsed).toEqual([1, undefined, undefined]);
	});

	it("handles Sets directly", () => {
		const s = new Set([1, 2, "three"]);
		const ser = serialize(s);
		const parsed = deserialize(ser);

		expect(parsed).toBeInstanceOf(Set);
		expect(parsed).toEqual(s);
	});

	it("handles Maps directly", () => {
		const m = new Map<string, string | number | boolean>([
			["one", 1],
			["two", "second"],
			["three", true],
		]);
		const ser = serialize(m);
		const parsed = deserialize(ser);

		expect(parsed).toBeInstanceOf(Map);
		expect(parsed).toEqual(m);
	});

	it("decodes nested special values (Set of Dates) and preserves shared refs", () => {
		const d = new Date("2024-02-02T00:00:00Z");
		const s = new Set([d, d]); // Set dedupes same ref -> size 1
		const data: any = { s, also: s, arr: [s, d] };

		const ser = serialize(data);
		const parsed: any = deserialize(ser);

		// Structure
		expect(parsed.s).toBeInstanceOf(Set);
		const items = Array.from(parsed.s.values());
		expect(items).toHaveLength(1);
		expect(items[0]).toBeInstanceOf(Date);
		expect(parsed.also).toBe(parsed.s); // shared Set reference
		expect(parsed.arr[0]).toBe(parsed.s); // shared Set
		expect(parsed.arr[1]).toBe(items[0]); // shared Date instance
	});

	it("handles cycles when special types are present", () => {
		const d = new Date("2024-03-03T00:00:00Z");
		const root: any = { when: d };
		root.self = root;
		const ser = serialize(root);
		const parsed: any = deserialize(ser);

		expect(parsed.self).toBe(parsed);
		expect(parsed.when).toBeInstanceOf(Date);
		expect(parsed.when.getTime()).toBe(d.getTime());
	});

	it("supports multiple special types in one structure", () => {
		const d1 = new Date("2020-01-01T00:00:00Z");
		const d2 = new Date("2030-01-01T00:00:00Z");
		const data: any = {
			list: [new Set([d1]), { deep: [new Set([d2, d1])] }],
			single: d2,
		};

		const ser = serialize(data);
		const parsed: any = deserialize(ser);

		expect(parsed.list[0]).toBeInstanceOf(Set);
		const firstSet = Array.from(parsed.list[0].values());
		expect(firstSet[0]).toBeInstanceOf(Date);
		expect(parsed.list[1].deep[0]).toBeInstanceOf(Set);
		const deepSet = Array.from(parsed.list[1].deep[0].values());
		expect(deepSet[0]).toBeInstanceOf(Date);
		expect(deepSet[1]).toBeInstanceOf(Date);
		expect(parsed.single).toBeInstanceOf(Date);
	});

	it("round trips Maps nested within plain objects", () => {
		const innerMap = new Map<string, number | string>([
			["layer", 1],
			["label", "record-0-layer-1"],
		]);
		const data = {
			level: 0,
			nested: {
				map: innerMap,
				info: { active: true },
			},
		};

		const serialized = serialize(data);
		const parsed = deserialize(serialized) as typeof data;

		expect(parsed.nested.map).toBeInstanceOf(Map);
		expect(parsed.nested.map.get("layer")).toBe(1);
		expect(parsed.nested.map.get("label")).toBe("record-0-layer-1");
		expect(parsed.nested.info).toEqual({ active: true });
	});

	it("handles arrays and objects", () => {
		const data: any = { a: 1, b: [2, 3, { c: "x" }] };
		const ser = serialize(data);
		const parsed = deserialize(ser);
		expect(parsed).toEqual(data);
	});

	it("preserves cycles and shared references", () => {
		const shared: any = { v: 42 };
		const root: any = { left: { shared }, right: { shared } };
		root.self = root;

		const ser = serialize(root);
		const parsed: any = deserialize(ser);

		expect(parsed.left.shared).toBe(parsed.right.shared);
		expect(parsed.self).toBe(parsed);
		expect(parsed.left.shared.v).toBe(42);
	});

	it("it handles dates and same references", () => {
		const d = new Date("2024-01-01T00:00:00Z");
		const data = { when: d, same: d } as const;
		const ser = serialize(data);
		const parsed: any = deserialize(ser);
		expect(parsed.when).toBeInstanceOf(Date);
		expect(parsed.when.getTime()).toBe(d.getTime());
		// shared reference must be preserved at same indices
		expect(parsed.when).toBe(parsed.same);
	});
	it("does not collide ref indices with string primitives", () => {
		const shared = { domain: ["a", "b"] };
		const data = { a: shared, b: shared };

		const ser = serialize(data);
		const parsed: any = deserialize(ser);

		expect(parsed.a.domain).toEqual(["a", "b"]);
		expect(parsed.a).toBe(parsed.b);
	});
	it("does not corrupt numeric primitives at ref indices", () => {
		const shared: any[] = [];
		const data = [shared, 0, shared];

		const ser = serialize(data);
		const parsed: any = deserialize(ser);

		expect(parsed[0]).toBe(parsed[2]);
		expect(parsed[1]).toBe(0);
		expect(parsed[1]).not.toBe(parsed);
	});
	it("does not collide date indices with string primitives", () => {
		const day = new Date("2024-01-02T00:00:00.000Z");
		const data = { label: "2024-01-02", day };

		const ser = serialize(data);
		const parsed: any = deserialize(ser);

		expect(parsed.label).toBe("2024-01-02");
		expect(typeof parsed.label).toBe("string");
		expect(parsed.day).toBeInstanceOf(Date);
		expect(parsed.day.toISOString()).toBe("2024-01-02T00:00:00.000Z");
	});
	it("decodes date literals as UTC midnight dates", () => {
		const ser: Serialized = [[[], [0], [], []], "2024-01-02"];
		const parsed = deserialize(ser) as Date;
		expect(parsed).toBeInstanceOf(Date);
		expect(parsed.toISOString()).toBe("2024-01-02T00:00:00.000Z");
	});
	it("throws on invalid date literals", () => {
		const ser: Serialized = [[[], [0], [], []], "2024-02-30"];
		expect(() => deserialize(ser)).toThrow("Invalid date literal: 2024-02-30");
	});

	it("coerces non-serializable values (functions/symbols) to null", () => {
		// Functions and symbols can't cross the wire; rather than crash the whole
		// payload we coerce them to null (like NaN). A common real-world source is a
		// React element (whose `$$typeof` is a symbol) leaking into a callback arg —
		// one stray element shouldn't nuke an entire form submission.
		const fromFunction: any = deserialize(serialize({ x: () => {}, keep: 1 } as any));
		expect(fromFunction).toEqual({ x: null, keep: 1 });
		const fromSymbol: any = deserialize(serialize({ x: Symbol("s"), keep: 2 } as any));
		expect(fromSymbol).toEqual({ x: null, keep: 2 });
	});

	it("rejects DOM nodes before traversing their React internals", () => {
		const input = document.createElement("input");
		Object.defineProperty(input, "__reactFiber$test", {
			enumerable: true,
			get: () => {
				throw new Error("React internals were traversed");
			},
		});

		expect(() => serialize({ input } as any)).toThrow(
			"Cannot serialize a DOM node in 'input'. Extract DOM events/elements before serializing.",
		);
	});

	it("rejects cross-realm-like DOM nodes without invoking IDL getters", () => {
		const nodePrototype = Object.create(Object.prototype);
		Object.defineProperties(nodePrototype, {
			[Symbol.toStringTag]: { value: "Node" },
			nodeType: {
				get() {
					throw new Error("IDL getter was invoked");
				},
			},
			nodeName: {
				get() {
					throw new Error("IDL getter was invoked");
				},
			},
			ownerDocument: {
				get() {
					throw new Error("IDL getter was invoked");
				},
			},
			cloneNode: { value() {} },
		});
		const form = Object.create(Object.create(nodePrototype));
		Object.defineProperty(form, "ownerDocument", { value: {} });
		Object.defineProperty(form, "__reactFiber$test", {
			enumerable: true,
			get: () => {
				throw new Error("React internals were traversed");
			},
		});

		expect(() => serialize({ form } as any)).toThrow(
			"Cannot serialize a DOM node in 'form'. Extract DOM events/elements before serializing.",
		);
	});

	it("does not mistake an inherited DOM-shaped application model for a Node", () => {
		class DomShapedRecord {
			payload = "keep";

			get ownerDocument(): never {
				throw new Error("application getter was invoked");
			}
		}
		Object.assign(DomShapedRecord.prototype, {
			nodeType: 1,
			nodeName: "record",
			addEventListener() {},
		});

		const parsed: any = deserialize(serialize({ record: new DomShapedRecord() }));
		expect(parsed).toEqual({ record: { payload: "keep" } });
	});

	it("rejects React fiber objects before recursively walking them", () => {
		const fiber = {
			tag: 0,
			key: null,
			elementType: null,
			type: null,
			stateNode: null,
			return: null,
			child: null,
			sibling: null,
			index: 0,
			ref: null,
			pendingProps: null,
			memoizedProps: null,
			updateQueue: null,
			memoizedState: null,
			dependencies: null,
			mode: 0,
			flags: 0,
			subtreeFlags: 0,
			deletions: null,
			lanes: 0,
			childLanes: 0,
			alternate: null,
		};

		expect(() => serialize({ fiber } as any)).toThrow(
			"Cannot serialize a React Fiber in 'fiber'. Extract DOM events/elements before serializing.",
		);
	});

	it("does not mistake Fiber-like application records for React internals", () => {
		class ApplicationModel {
			payload = "keep";

			get tag(): never {
				throw new Error("inherited tag getter was invoked");
			}
		}
		const data = {
			shape: {
				tag: 0,
				return: null,
				child: null,
				sibling: null,
				stateNode: null,
				memoizedProps: null,
			},
			expandoNamedData: { "__reactFiber$business": "keep" },
			model: new ApplicationModel(),
		};

		const parsed: any = deserialize(serialize(data));
		expect(parsed).toEqual({
			shape: data.shape,
			expandoNamedData: data.expandoNamedData,
			model: { payload: "keep" },
		});
	});

	it("keeps indices aligned when a dropped leaf sits among shared refs and Dates", () => {
		// The serializer tracks refs/dates by positional node index, so a coerced leaf
		// must consume an index just like the primitive it becomes. This interleaves a
		// function (→ null), a shared ref, and a Date to prove round-trips stay aligned.
		const shared = { v: 1 };
		const data = {
			a: shared,
			arr: [() => {}, shared],
			d: new Date("1970-01-01T00:00:00.000Z"),
		};

		const parsed: any = deserialize(serialize(data as any));

		expect(parsed.arr[0]).toBe(null);
		expect(parsed.a).toBe(parsed.arr[1]); // shared reference preserved
		expect(parsed.a).toEqual({ v: 1 });
		expect(parsed.d).toBeInstanceOf(Date);
		expect(parsed.d.toISOString()).toBe("1970-01-01T00:00:00.000Z");
	});

	it("throws a clear, contextual error on genuinely unsupported types (bigint)", () => {
		// Unlike functions/symbols, a bigint is real data the caller likely intended to
		// send, so we error (with the path) rather than coercing it away. The message is
		// built from `typeof`, never the raw value — interpolating a symbol here is what
		// used to throw the cryptic "Cannot convert a symbol to a string".
		expect(() => serialize({ amount: 10n } as any)).toThrow(
			"Cannot serialize value of type 'bigint' in 'amount'.",
		);
	});

	it("coerces NaN to null", () => {
		const data = { value: NaN };
		const ser = serialize(data);
		const parsed = deserialize(ser);
		expect(parsed).toEqual({ value: null });
	});

	it("throws on Infinity with context", () => {
		expect(() => serialize({ value: Infinity })).toThrow(
			"Cannot serialize Infinity in 'value'. NaN and Infinity are not supported because they cannot be serialized to JSON.",
		);
	});

	it("throws on -Infinity with context", () => {
		expect(() => serialize({ value: -Infinity })).toThrow(
			"Cannot serialize -Infinity in 'value'. NaN and Infinity are not supported because they cannot be serialized to JSON.",
		);
	});

	it("coerces NaN in nested objects to null", () => {
		const data = { outer: { inner: NaN } };
		const ser = serialize(data);
		const parsed = deserialize(ser);
		expect(parsed).toEqual({ outer: { inner: null } });
	});

	it("coerces NaN in arrays to null", () => {
		const data = { values: [1, 2, NaN, 4] };
		const ser = serialize(data);
		const parsed = deserialize(ser);
		expect(parsed).toEqual({ values: [1, 2, null, 4] });
	});

	it("coerces top-level NaN to null", () => {
		const ser = serialize(NaN);
		const parsed = deserialize(ser);
		expect(parsed).toBeNull();
	});

	it("allows valid finite numbers", () => {
		const data = { a: 1, b: 3.14, c: -100, d: 0, e: Number.MAX_VALUE };
		const ser = serialize(data);
		const parsed = deserialize(ser);
		expect(parsed).toEqual(data);
	});
});
