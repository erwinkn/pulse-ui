import { describe, expect, it } from "bun:test";
import { deserialize, serialize, type Serialized } from "./serializer";

function crossJSON<Data>(value: Data): Data {
	return JSON.parse(JSON.stringify(value));
}

function wireSerialize(value: unknown): Serialized {
	return crossJSON(serialize(value));
}

function wireRoundTrip(value: unknown): any {
	return deserialize(wireSerialize(value)) as any;
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

function randomPortableValue(
	random: () => number,
	depth: number,
	objects: object[] = [],
): unknown {
	const leaf = () => {
		switch (Math.floor(random() * 7)) {
			case 0:
				return null;
			case 1:
				return undefined;
			case 2:
				return random() < 0.5;
			case 3:
				return Math.floor(random() * 21) - 10;
			case 4:
				return random() < 0.5 ? "text" : "😀";
			case 5:
				return Number.NaN;
			default:
				return random() * 20 - 10;
		}
	};

	if (depth === 0 || random() < 0.25) return leaf();
	if (objects.length > 0 && random() < 0.12) {
		return objects[Math.floor(random() * objects.length)];
	}

	const kind = Math.floor(random() * 5);
	const size = Math.floor(random() * 4);
	if (kind === 0) {
		const value: unknown[] = [];
		objects.push(value);
		for (let index = 0; index < size; index += 1) {
			value.push(randomPortableValue(random, depth - 1, objects));
		}
		return value;
	}
	if (kind === 1) {
		const value: Record<string, unknown> = Object.create(null);
		objects.push(value);
		for (let index = 0; index < size; index += 1) {
			const key = index === 0 && random() < 0.2 ? "__proto__" : `key-${index}`;
			value[key] = randomPortableValue(random, depth - 1, objects);
		}
		return value;
	}
	if (kind === 2) {
		const value = new Map<string, unknown>();
		objects.push(value);
		for (let index = 0; index < size; index += 1) {
			value.set(`key-${index}`, randomPortableValue(random, depth - 1, objects));
		}
		return value;
	}
	if (kind === 3) {
		const value = new Set<unknown>();
		objects.push(value);
		for (let index = 0; index < size; index += 1) {
			value.add(`set-${index}`);
		}
		return value;
	}
	const value = new Date(Date.UTC(2020 + Math.floor(random() * 10), 0, 1));
	objects.push(value);
	return value;
}

describe("serialization", () => {
	it("keeps plain JSON plain and compact", () => {
		const value = { a: 1, b: [2, "x", true, null] };

		expect(serialize(value)).toEqual([5, value]);
		expect(JSON.stringify(serialize(value))).toBe('[5,{"a":1,"b":[2,"x",true,null]}]');
		expect(wireRoundTrip(value)).toEqual(value);
	});

	it("accepts unknown input at the deserialize boundary", () => {
		const payload: unknown = JSON.parse('[5,{"value":1}]');

		expect(deserialize(payload)).toEqual({ value: 1 });
	});

	it("normalizes undefined by structural position and preserves null", () => {
		const sparse = new Array(3);
		sparse[1] = undefined;
		sparse[2] = null;

		expect(serialize(undefined)).toEqual([5, null]);
		expect(serialize({ omitted: undefined, kept: null })).toEqual([5, { kept: null }]);
		expect(serialize(sparse)).toEqual([5, [null, null, null]]);
		expect(
			serialize(
				new Map<string, unknown>([
					["missing", undefined],
					["null", null],
				]),
			),
		).toEqual([
			5,
			["$", "m", [["missing", null], ["null", null]]],
		]);
		expect(deserialize([5, null])).toBeNull();
	});

	it("normalizes NaN and -0 but rejects non-finite numbers", () => {
		expect(serialize({ root: Number.NaN, nested: [Number.NaN] })).toEqual([
			5,
			{ root: null, nested: [null] },
		]);
		expect(() => serialize(Infinity)).toThrow("non-finite number");
		expect(() => serialize(-Infinity)).toThrow("non-finite number");
		expect(serialize(-0)).toEqual([5, 0]);
		expect(Object.is((serialize(-0) as unknown[])[1], -0)).toBeFalse();
		expect(() => deserialize([5, Number.NaN] as Serialized)).toThrow("non-finite number");
		expect(Object.is(deserialize([5, -0]), -0)).toBeFalse();
	});

	it("round-trips doubles beyond the safe integer range via the big-float marker", () => {
		expect(serialize(2 ** 53)).toEqual([5, ["$", "f", 2 ** 53]]);
		expect(serialize(1e300)).toEqual([5, ["$", "f", 1e300]]);
		expect(serialize(new Set([1e300]))).toEqual([5, ["$", "s", [["$", "f", 1e300]]]]);
		expect(deserialize([5, ["$", "f", 1e300]] as Serialized)).toBe(1e300);
		expect(deserialize([5, ["$", "s", [["$", "f", 1e300]]]] as Serialized)).toEqual(
			new Set([1e300]),
		);
		expect(() => deserialize([5, 2 ** 53] as Serialized)).toThrow("big-float marker");
		expect(() => deserialize([5, 1e300] as Serialized)).toThrow("big-float marker");
		for (const payload of [5, 2 ** 53 - 1, "1e300", Infinity, Number.NaN]) {
			expect(() => deserialize([5, ["$", "f", payload]] as Serialized)).toThrow(
				"Malformed big-float marker",
			);
		}
		expect(() => deserialize([5, ["$", "f", 1e300, null]] as Serialized)).toThrow(
			"Malformed",
		);
	});

	it("uses exact temporal, Map, Set, and compact reference markers", () => {
		const when = new Date("2024-01-02T03:04:05.678Z");
		const shared = { when };
		const value = {
			first: shared,
			second: shared,
			map: new Map<string, unknown>([
				["second", 2],
				["first", when],
			]),
			set: new Set(["z", 2, 1]),
		};

		expect(serialize(value)).toEqual([
			5,
			{
				first: { when: ["$", "t", "2024-01-02T03:04:05.678Z"] },
				second: ["$", 1],
				map: ["$", "m", [["second", 2], ["first", ["$", 2]]]],
				set: ["$", "s", [1, 2, "z"]],
			},
		]);

		const parsed = wireRoundTrip(value);
		expect(parsed.first).toBe(parsed.second);
		expect(parsed.first.when).toBe(parsed.map.get("first"));
		expect(parsed.map).toBeInstanceOf(Map);
		expect([...parsed.map.keys()]).toEqual(["second", "first"]);
		expect(parsed.set).toEqual(new Set([1, 2, "z"]));
	});

	it("escapes source arrays beginning with '$'", () => {
		const value = ["$", 0, ["$", "t", "source data"]];

		expect(serialize(value)).toEqual([
			5,
			["$", "a", ["$", 0, ["$", "a", ["$", "t", "source data"]]]],
		]);
		expect(wireRoundTrip(value)).toEqual(value);
	});

	it("preserves cycles, identity, and own __proto__ keys", () => {
		const root = JSON.parse('{"__proto__":{"safe":true}}') as Record<string, any>;
		const shared: any[] = [];
		root.first = shared;
		root.second = shared;
		root.self = root;
		shared.push(root);

		const parsed = wireRoundTrip(root);
		expect(parsed.self).toBe(parsed);
		expect(parsed.first).toBe(parsed.second);
		expect(parsed.first[0]).toBe(parsed);
		expect(Object.hasOwn(parsed, "__proto__")).toBeTrue();
		expect(parsed.__proto__).toEqual({ safe: true });
		expect(Object.getPrototypeOf(parsed)).toBe(Object.prototype);
	});

	it("sorts Sets canonically by portable cross-runtime order", () => {
		const when = new Date("2024-01-02T00:00:00.000Z");
		const value = new Set<unknown>([
			when,
			"😀",
			"\ue000",
			"b",
			10,
			2,
			1.5,
			-10,
			true,
			false,
			null,
		]);

		expect(serialize(value)).toEqual([
			5,
			[
				"$",
				"s",
				[
					null,
					false,
					true,
					-10,
					1.5,
					2,
					10,
					"b",
					"\ue000",
					"😀",
					["$", "t", "2024-01-02T00:00:00.000Z"],
				],
			],
		]);
	});

	it("rejects Set collisions after normalization", () => {
		expect(serialize(new Set([undefined]))).toEqual([5, ["$", "s", [null]]]);
		expect(() => serialize(new Set([undefined, null]))).toThrow(
			"cross-runtime-colliding",
		);
		expect(() => serialize(new Set([Number.NaN, null]))).toThrow(
			"cross-runtime-colliding",
		);
		expect(() => serialize(new Set([false, 0]))).toThrow("cross-runtime-colliding");
		expect(() => serialize(new Set([true, 1]))).toThrow("cross-runtime-colliding");
		expect(() =>
			serialize(
				new Set([
					new Date("2024-01-01T00:00:00.000Z"),
					new Date("2024-01-01T00:00:00.000Z"),
				]),
			),
		).toThrow("cross-runtime-colliding");
		expect(() => serialize(new Set([[1]]))).toThrow("non-portable Set value");
	});

	it("uses builtin Date, Map, and Set storage without user overrides", () => {
		class MisleadingMap extends Map<string, unknown> {
			override entries(): MapIterator<[string, unknown]> {
				return new Map<string, unknown>([["fake", 0]]).entries();
			}
		}
		class MisleadingSet extends Set<unknown> {
			override values(): SetIterator<unknown> {
				return new Set<unknown>(["fake"]).values();
			}
		}
		class MisleadingDate extends Date {
			override toISOString(): string {
				return "fake";
			}
		}

		expect(serialize(new MisleadingMap([["actual", 1]]))).toEqual([
			5,
			["$", "m", [["actual", 1]]],
		]);
		expect(serialize(new MisleadingSet([2, 1]))).toEqual([5, ["$", "s", [1, 2]]]);
		expect(serialize(new MisleadingDate("2024-01-01T00:00:00.000Z"))).toEqual([
			5,
			["$", "t", "2024-01-01T00:00:00.000Z"],
		]);
	});

	it("reads enumerable plain-object and array accessors once", () => {
		let objectReads = 0;
		let arrayReads = 0;
		const object = {
			get value() {
				objectReads += 1;
				return 1;
			},
		};
		const array: number[] = [];
		Object.defineProperty(array, "0", {
			enumerable: true,
			get() {
				arrayReads += 1;
				return 2;
			},
		});
		array.length = 1;

		expect(serialize({ object, array })).toEqual([5, { object: { value: 1 }, array: [2] }]);
		expect(objectReads).toBe(1);
		expect(arrayReads).toBe(1);
	});

	it("rejects unsupported values and non-plain objects with paths", () => {
		class Value {
			value = 1;
		}

		expect(() => serialize({ nested: { fn: () => {} } })).toThrow("$.nested.fn");
		expect(() => serialize({ nested: Symbol("x") })).toThrow("$.nested");
		expect(() => serialize({ amount: 10n })).toThrow("$.amount");
		expect(() => serialize({ value: new Value() })).toThrow("prototype Value at $.value");
		expect(() => serialize(new Uint8Array([1, 2]))).toThrow("prototype Uint8Array");
		expect(() => serialize(new Map([[1, "value"]]))).toThrow("Map key");
	});

	it("rejects ill-formed Unicode in values and keys", () => {
		expect(() => serialize({ value: "\ud800" })).toThrow("ill-formed Unicode");
		const value: Record<string, unknown> = {};
		value["\ud800"] = 1;
		expect(() => serialize(value)).toThrow("ill-formed Unicode");
		expect(() => deserialize([5, "\ud800"])).toThrow("ill-formed Unicode");
	});

	it("rejects invalid and out-of-range Dates", () => {
		const yearZero = new Date(0);
		yearZero.setUTCFullYear(0);
		const yearTenThousand = new Date(0);
		yearTenThousand.setUTCFullYear(10_000);

		expect(() => serialize(new Date("invalid"))).toThrow("invalid Date");
		expect(() => serialize(yearZero)).toThrow("year range 0001-9999");
		expect(() => serialize(yearTenThousand)).toThrow("year range 0001-9999");
		expect(() => deserialize([5, ["$", "t", "2024-01-02T03:04:05Z"]])).toThrow(
			"Invalid datetime literal",
		);
		expect(() =>
			deserialize([5, ["$", "t", "2024-02-30T00:00:00.000Z"]]),
		).toThrow("Invalid datetime literal");
	});

	it("strictly validates envelopes, markers, Maps, Sets, and references", () => {
		expect(() => deserialize([5] as any)).toThrow("Wire payload must be");
		expect(() => deserialize([5, ["$", 0]])).toThrow("Dangling reference");
		expect(() => deserialize([5, { before: ["$", 1], after: {} }] as any)).toThrow(
			"Dangling reference",
		);
		expect(() => deserialize([5, ["$", "a", []]] as any)).toThrow("must begin");
		expect(() => deserialize([5, ["$", "m", [["a", 1], ["a", 2]]]] as any)).toThrow(
			"Duplicate Map key",
		);
		expect(() => deserialize([5, ["$", "s", [2, 1]]] as any)).toThrow(
			"not canonically ordered",
		);
		expect(() => deserialize([5, ["$", "s", [false, 0]]] as any)).toThrow(
			"cross-runtime-colliding",
		);
		expect(() => deserialize([5, ["$", "s", [[]]]] as any)).toThrow(
			"non-portable Set value",
		);
	});

	it("is stable across JSON for seeded portable-domain graphs", () => {
		for (let seed = 1; seed <= 500; seed += 1) {
			const value = randomPortableValue(seededRandom(seed), 4);
			const wire = wireSerialize(value);
			const parsed = deserialize(wire);
			const nextWire = wireSerialize(parsed);
			if (JSON.stringify(nextWire) !== JSON.stringify(wire)) {
				throw new Error(
					`Wire round trip changed seeded case ${seed}: ${JSON.stringify(wire)} -> ${JSON.stringify(nextWire)}`,
				);
			}
		}
	});
});
