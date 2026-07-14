import { describe, expect, it } from "bun:test";
import {
	DateOnly,
	deserialize,
	type Serialized,
	serialize,
} from "./marker-serializer";

function wireSerialize(data: unknown): Serialized {
	return JSON.parse(JSON.stringify(serialize(data)));
}

function wireRoundTrip(data: unknown): any {
	return deserialize(wireSerialize(data));
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

function randomSafeInteger(random: () => number): number {
	return Math.floor((random() - 0.5) * 1000);
}

function randomNumber(random: () => number): number {
	if (random() < 0.5) {
		return randomSafeInteger(random);
	}
	return Math.round((random() * 2000 - 1000) * 1000) / 1000;
}

function randomString(random: () => number): string {
	const variants = ["plain", "value", "$", "__proto__", "2024-01-02", "key-1"];
	return variants[Math.floor(random() * variants.length)];
}

function randomDate(random: () => number): Date {
	return new Date(
		Date.UTC(
			2020 + Math.floor(random() * 5),
			Math.floor(random() * 12),
			1 + Math.floor(random() * 28),
			Math.floor(random() * 24),
			Math.floor(random() * 60),
			Math.floor(random() * 60),
			Math.floor(random() * 1000),
		),
	);
}

function randomDateOnly(random: () => number): DateOnly {
	return new DateOnly(
		2020 + Math.floor(random() * 5),
		1 + Math.floor(random() * 12),
		1 + Math.floor(random() * 28),
	);
}

function randomSetLeaf(
	random: () => number,
	objects: object[],
): null | boolean | number | string | Date | DateOnly {
	const kind = Math.floor(random() * 6);
	if (kind === 0) {
		return null;
	}
	if (kind === 1) {
		return random() < 0.5;
	}
	if (kind === 2) {
		return randomNumber(random);
	}
	if (kind === 3) {
		return randomString(random);
	}
	if (kind === 4) {
		const date = randomDate(random);
		objects.push(date);
		return date;
	}
	const dateOnly = randomDateOnly(random);
	objects.push(dateOnly);
	return dateOnly;
}

function randomPortableValue(
	random: () => number,
	depth: number,
	objects: object[] = [],
): unknown {
	if (depth === 0) {
		const leafKind = Math.floor(random() * 6);
		switch (leafKind) {
			case 0:
				return null;
			case 1:
				return random() < 0.5;
			case 2:
				return randomNumber(random);
			case 3:
				return randomString(random);
			case 4: {
				const date = randomDate(random);
				objects.push(date);
				return date;
			}
			default: {
				const dateOnly = randomDateOnly(random);
				objects.push(dateOnly);
				return dateOnly;
			}
		}
	}

	if (objects.length > 0 && random() < 0.18) {
		return objects[Math.floor(random() * objects.length)];
	}

	const kind = Math.floor(random() * 7);
	if (kind === 0) {
		return randomPortableValue(random, 0, objects);
	}
	if (kind === 1) {
		const arr: unknown[] = [];
		objects.push(arr);
		const size = Math.floor(random() * 4);
		if (size > 0 && random() < 0.35) {
			arr.push("$");
		}
		while (arr.length < size) {
			arr.push(randomPortableValue(random, depth - 1, objects));
		}
		if (random() < 0.2) {
			arr.push(arr);
		}
		return arr;
	}
	if (kind === 2) {
		const obj: Record<string, unknown> = Object.create(null);
		objects.push(obj);
		const size = Math.floor(random() * 4);
		for (let index = 0; index < size; index += 1) {
			const key =
				index === 0 && random() < 0.3
					? "__proto__"
					: random() < 0.4
						? String(index)
						: `key-${index}`;
			obj[key] = randomPortableValue(random, depth - 1, objects);
		}
		if (random() < 0.2) {
			obj.self = obj;
		}
		return obj;
	}
	if (kind === 3) {
		const map = new Map<string, unknown>();
		objects.push(map);
		const size = Math.floor(random() * 4);
		for (let index = 0; index < size; index += 1) {
			const key = random() < 0.5 ? String(index) : `key-${index}`;
			map.set(key, randomPortableValue(random, depth - 1, objects));
		}
		if (random() < 0.2) {
			map.set("self", map);
		}
		return map;
	}
	if (kind === 4) {
		const set = new Set<unknown>();
		objects.push(set);
		const size = Math.floor(random() * 4);
		while (set.size < size) {
			const value = randomSetLeaf(random, objects);
			if ((value === true && set.has(1)) || (value === 1 && set.has(true))) {
				continue;
			}
			if ((value === false && set.has(0)) || (value === 0 && set.has(false))) {
				continue;
			}
			if (
				value instanceof Date &&
				Array.from(set).some(
					(entry) =>
						entry instanceof Date &&
						entry.toISOString() === value.toISOString(),
				)
			) {
				continue;
			}
			if (
				value instanceof DateOnly &&
				Array.from(set).some(
					(entry) =>
						entry instanceof DateOnly && entry.toString() === value.toString(),
				)
			) {
				continue;
			}
			set.add(value);
		}
		return set;
	}
	if (kind === 5) {
		const date = randomDate(random);
		objects.push(date);
		return date;
	}
	const dateOnly = randomDateOnly(random);
	objects.push(dateOnly);
	return dateOnly;
}

describe("v5 serialization", () => {
	it("keeps plain JSON as plain JSON and compact", () => {
		const value = { a: 1, b: [2, "x", true, null] };
		expect(serialize(value)).toEqual([5, value]);
		expect(JSON.stringify(serialize(value)).length).toBe(33);
	});

	it("serializes DateOnly, datetime, Map, and Set with exact compact markers", () => {
		const day = new DateOnly(2024, 1, 2);
		const when = new Date("2024-01-02T03:04:05.678Z");
		const map = new Map<string, unknown>([
			["b", 2],
			["a", day],
		]);
		const set = new Set([2, 1, "z"]);

		expect(serialize(day)).toEqual([5, ["$", "d", "2024-01-02"]]);
		expect(JSON.stringify(serialize(day)).length).toBe(26);

		expect(serialize(when)).toEqual([
			5,
			["$", "t", "2024-01-02T03:04:05.678Z"],
		]);
		expect(JSON.stringify(serialize(when)).length).toBe(40);

		expect(serialize(map)).toEqual([
			5,
			[
				"$",
				"m",
				[
					["b", 2],
					["a", ["$", "d", "2024-01-02"]],
				],
			],
		]);
		expect(JSON.stringify(serialize(map)).length).toBe(52);

		expect(serialize(set)).toEqual([5, ["$", "s", [1, 2, "z"]]]);
		expect(JSON.stringify(serialize(set)).length).toBe(23);
	});

	it("reads built-in Map and Set storage instead of overridden iterators", () => {
		class MisleadingMap extends Map<string, unknown> {
			override entries(): MapIterator<[string, unknown]> {
				return new Map<string, unknown>([["fake", 0]]).entries();
			}
		}

		class MisleadingSet extends Set<unknown> {
			override values(): SetIterator<unknown> {
				return new Set<unknown>(["fake"]).values();
			}

			override [Symbol.iterator](): SetIterator<unknown> {
				return this.values();
			}
		}

		expect(serialize(new MisleadingMap([["actual", 1]]))).toEqual([
			5,
			["$", "m", [["actual", 1]]],
		]);
		expect(serialize(new MisleadingSet([2, 1]))).toEqual([
			5,
			["$", "s", [1, 2]],
		]);
	});

	it("escapes plain arrays that begin with '$'", () => {
		const value = ["$", 1, new DateOnly(2024, 1, 2)];
		expect(serialize(value)).toEqual([
			5,
			["$", "a", ["$", 1, ["$", "d", "2024-01-02"]]],
		]);
		expect(wireRoundTrip(value)).toEqual(value);
	});

	it("uses deterministic first-encounter ids for shared refs and cycles", () => {
		const shared = { value: 1 };
		const graph = { first: shared, second: shared };
		const day = new DateOnly(2024, 1, 2);
		const dayGraph = { first: day, second: day };
		const cycle: Record<string, unknown> = { name: "root" };
		cycle.self = cycle;

		expect(wireSerialize(graph)).toEqual([
			5,
			{
				first: { value: 1 },
				second: ["$", "r", 1],
			},
		]);
		expect(wireSerialize(dayGraph)).toEqual([
			5,
			{
				first: ["$", "d", "2024-01-02"],
				second: ["$", "r", 1],
			},
		]);
		expect(wireSerialize(cycle)).toEqual([
			5,
			{ name: "root", self: ["$", "r", 0] },
		]);

		const parsed = wireRoundTrip(graph);
		expect(parsed.first).toBe(parsed.second);
		const parsedDayGraph = wireRoundTrip(dayGraph);
		expect(parsedDayGraph.first).toBe(parsedDayGraph.second);
	});

	it("preserves own __proto__ safely during decode", () => {
		const value = JSON.parse('{"__proto__":{"safe":true},"keep":1}') as Record<
			string,
			unknown
		>;
		const parsed = wireRoundTrip(value);

		expect(Object.hasOwn(parsed, "__proto__")).toBeTrue();
		expect(parsed.keep).toBe(1);
		expect(parsed.__proto__).toEqual({ safe: true });
		expect(Object.getPrototypeOf(parsed)).toBe(Object.prototype);
	});

	it("round trips DateOnly, Date, Map, Set, refs, and cycles across JSON", () => {
		const day = new DateOnly(2024, 1, 2);
		const when = new Date("2024-01-02T03:04:05.678Z");
		const shared = { label: "shared", when };
		const map = new Map<string, unknown>([
			["0", shared],
			["1", day],
		]);
		const set = new Set<unknown>([day, when, "x", 2]);
		const root: Record<string, unknown> = {
			map,
			set,
			shared,
			day,
			nothing: null,
		};
		root.self = root;

		const wire = wireSerialize(root);
		const parsed = deserialize<any>(wire);

		expect(parsed.self).toBe(parsed);
		expect(parsed.shared).toBe(parsed.map.get("0"));
		expect(parsed.shared.when).toBeInstanceOf(Date);
		expect(parsed.day).toBeInstanceOf(DateOnly);
		expect(parsed.day.toString()).toBe("2024-01-02");
		expect(parsed.set).toBeInstanceOf(Set);
		expect(parsed.nothing).toBeNull();
		expect(wireSerialize(parsed)).toEqual(wire);
	});

	it("orders Sets canonically regardless of insertion order", () => {
		const left = new Set<unknown>([
			"😀",
			"\ue000",
			"z",
			10,
			2,
			1.5,
			-10,
			new DateOnly(2024, 1, 2),
			false,
			1,
			null,
		]);
		const right = new Set<unknown>([...left].reverse());

		expect(serialize(left)).toEqual(serialize(right));
		expect(serialize(left)).toEqual([
			5,
			[
				"$",
				"s",
				[
					null,
					false,
					-10,
					1,
					1.5,
					2,
					10,
					"z",
					"\ue000",
					"😀",
					["$", "d", "2024-01-02"],
				],
			],
		]);
	});

	it("rejects unsupported values with useful paths", () => {
		const sparse = new Array(2);
		sparse[1] = "value";
		let accessorCalls = 0;
		const accessorArray: string[] = [];
		Object.defineProperty(accessorArray, "0", {
			enumerable: true,
			get() {
				accessorCalls += 1;
				return "$";
			},
		});

		expect(() => serialize({ value: undefined })).toThrow(
			"Cannot serialize undefined at $.value",
		);
		expect(() => serialize({ items: sparse })).toThrow(
			"Cannot serialize sparse array at $.items[0]",
		);
		expect(() => serialize(accessorArray)).toThrow(
			"Cannot serialize malformed array at $[0]",
		);
		expect(accessorCalls).toBe(0);
		expect(() => serialize({ items: [() => {}] })).toThrow(
			"Cannot serialize function at $.items[0]",
		);
		expect(() => serialize({ marker: Symbol("x") })).toThrow(
			"Cannot serialize symbol at $.marker",
		);
		expect(() => serialize({ [Symbol("key")]: "value" })).toThrow(
			"Cannot serialize symbol-keyed property at $: Symbol(key)",
		);
		expect(() => serialize({ amount: 10n })).toThrow(
			"Cannot serialize bigint at $.amount",
		);
		expect(() => serialize({ value: Number.NaN })).toThrow(
			"Cannot serialize non-finite number at $.value",
		);
		expect(() => serialize({ value: Infinity })).toThrow(
			"Cannot serialize non-finite number at $.value",
		);
		expect(() => serialize({ value: -0 })).toThrow(
			"Cannot serialize negative zero at $.value",
		);
		expect(() => serialize({ value: 2 ** 53 })).toThrow(
			"Cannot serialize unsafe integer at $.value",
		);
		expect(() => serialize({ value: "\ud800" })).toThrow(
			"Cannot serialize surrogate code point at $.value",
		);
		expect(() => deserialize([5, "\ud800"])).toThrow(
			"Cannot deserialize surrogate code point at $",
		);
		const normalizedZero = deserialize<number>([5, -0]);
		expect(normalizedZero).toBe(0);
		expect(Object.is(normalizedZero, -0)).toBe(false);
		const negativeZeroRef = deserialize<any>([5, [["$", "r", -0]]]);
		expect(negativeZeroRef[0]).toBe(negativeZeroRef);
	});

	it("rejects invalid dates and date literals", () => {
		const invalidDate = new Date("not-a-date");
		const mutatedDateOnly = new DateOnly(2024, 2, 29);
		(mutatedDateOnly as any).day = 30;
		const yearZero = new Date(0);
		yearZero.setUTCFullYear(0);
		const yearTenThousand = new Date(0);
		yearTenThousand.setUTCFullYear(10_000);

		expect(() => serialize(invalidDate)).toThrow(
			"Cannot serialize invalid Date at $",
		);
		expect(() => serialize({ day: mutatedDateOnly })).toThrow(
			"Invalid date literal at $.day: 2024-02-30",
		);
		expect(() => serialize(yearZero)).toThrow("supported year range 0001-9999");
		expect(() => serialize(yearTenThousand)).toThrow(
			"supported year range 0001-9999",
		);
		expect(() => new DateOnly(2024, 2, 30)).toThrow(
			"Invalid date literal at $",
		);
		expect(() => deserialize([5, ["$", "d", "2024-02-30"]])).toThrow(
			"Invalid date literal at $: 2024-02-30",
		);
		expect(() => deserialize([5, ["$", "d", "2024-01-02\n"]])).toThrow(
			"Invalid date literal at $: 2024-01-02",
		);
		expect(() => deserialize([5, ["$", "t", "2024-01-02T03:04:05Z"]])).toThrow(
			"Invalid datetime literal at $: 2024-01-02T03:04:05Z",
		);
		expect(() =>
			deserialize([5, ["$", "t", "2024-01-02T03:04:05.678901Z"] as any]),
		).toThrow("Invalid datetime literal at $: 2024-01-02T03:04:05.678901Z");
	});

	it("rejects non-string Map keys and non-portable Set values", () => {
		expect(() => serialize(new Map([[1, "value"]]))).toThrow(
			"Cannot serialize Map with non-string key at $",
		);
		expect(() => serialize(new Set([[1, 2]]))).toThrow(
			"Cannot serialize non-portable Set value at $<set:0>",
		);
		expect(() => serialize(new Set([true, 1]))).toThrow(
			"Python-equality collision",
		);
		expect(() => serialize(new Set([false, 0]))).toThrow(
			"Python-equality collision",
		);
		expect(() =>
			serialize(
				new Set([
					new Date("2024-01-02T00:00:00.000Z"),
					new Date("2024-01-02T00:00:00.000Z"),
				]),
			),
		).toThrow("Python-equality collision");
		expect(() =>
			serialize(new Set([new DateOnly(2024, 1, 2), new DateOnly(2024, 1, 2)])),
		).toThrow("Python-equality collision");
	});

	it("validates malformed wire envelopes, markers, refs, and Set payloads strictly", () => {
		expect(() => deserialize([4, null] as any)).toThrow(
			"Unknown serialization version: 4",
		);
		expect(() => deserialize(["5", null] as any)).toThrow(
			"Unknown serialization version: 5",
		);
		expect(() => deserialize([5] as any)).toThrow(
			"Malformed serialized envelope",
		);
		expect(() => deserialize([5, ["$", "x"]] as any)).toThrow(
			"Unknown marker tag 'x' at $",
		);
		expect(() => deserialize([5, ["$", "a"]] as any)).toThrow(
			"Malformed marker 'a' at $",
		);
		expect(() => deserialize([5, ["$", 1, []]] as any)).toThrow(
			"Malformed marker at $",
		);
		expect(() => deserialize([5, ["$", "r", 0]])).toThrow(
			"Dangling reference to id 0 at $",
		);
		expect(() =>
			deserialize([
				5,
				{ before: ["$", "r", 1], after: { ok: true } },
			] as any),
		).toThrow("Dangling reference to id 1 at $.before");
		expect(() => deserialize([5, ["$", "i", 0, {}]] as any)).toThrow(
			"Unknown marker tag 'i' at $",
		);
		expect(() => deserialize([5, ["$", "i", -1, {}]] as any)).toThrow(
			"Unknown marker tag 'i' at $",
		);
		expect(() => deserialize([5, ["$", "m", [{ bad: true }]]] as any)).toThrow(
			"Map entry must be [string, value] at $[0]",
		);
		expect(() =>
			deserialize([
				5,
				[
					"$",
					"m",
					[
						["key", 1],
						["key", 2],
					],
				],
			]),
		).toThrow("Duplicate Map key 'key' at $[1]");
		expect(() => deserialize([5, ["$", "a", [], "extra"]] as any)).toThrow(
			"Malformed marker 'a' at $",
		);
		expect(() => deserialize([5, ["$", "a", []]] as any)).toThrow(
			"Escaped array payload must begin with '$' at $",
		);
		expect(() => deserialize([5, ["$", "a", [1]]] as any)).toThrow(
			"Escaped array payload must begin with '$' at $",
		);
		expect(() => deserialize([5, ["$", "s", [["$", "m", []]]]] as any)).toThrow(
			"Cannot deserialize non-portable Set value at $<set:0>",
		);
		expect(() => deserialize([5, ["$", "s", [true, 1]]])).toThrow(
			"Set contains duplicate portable value at $<set:1>",
		);
		expect(() => deserialize([5, ["$", "s", [2, 1]]])).toThrow(
			"Set entries are not canonically ordered at $<set:1>",
		);
		const symbolRecord = { [Symbol("key")]: "value" };
		expect(() => deserialize([5, symbolRecord] as any)).toThrow(
			"Malformed wire object at $",
		);
		expect(() => deserialize([5, new Map()] as any)).toThrow(
			"Malformed wire object at $",
		);
		expect(() =>
			deserialize([5, Object.create({ inherited: true })] as any),
		).toThrow("Malformed wire object at $");
		const hiddenRecord = {};
		Object.defineProperty(hiddenRecord, "hidden", { value: true });
		expect(() => deserialize([5, hiddenRecord] as any)).toThrow(
			"Malformed wire object at $",
		);
		let accessorCalls = 0;
		const accessorRecord = {
			get value() {
				accessorCalls += 1;
				return true;
			},
		};
		expect(() => deserialize([5, accessorRecord] as any)).toThrow(
			"Malformed wire object at $",
		);
		expect(accessorCalls).toBe(0);

		let arrayAccessorCalls = 0;
		const accessorArray: unknown[] = [];
		Object.defineProperty(accessorArray, "0", {
			enumerable: true,
			get() {
				arrayAccessorCalls += 1;
				return "$";
			},
		});
		expect(() => deserialize([5, accessorArray] as any)).toThrow(
			"Malformed wire array at $[0]",
		);
		expect(arrayAccessorCalls).toBe(0);

		const hiddenArray: unknown[] = [];
		Object.defineProperty(hiddenArray, "hidden", { value: true });
		expect(() => deserialize([5, hiddenArray] as any)).toThrow(
			"Malformed wire array at $",
		);

		const symbolArray = Object.assign([], { [Symbol("key")]: true });
		expect(() => deserialize([5, symbolArray] as any)).toThrow(
			"Malformed wire array at $",
		);

		let structuralAccessorCalls = 0;
		const mapEntries: unknown[] = [];
		Object.defineProperty(mapEntries, "0", {
			enumerable: true,
			get() {
				structuralAccessorCalls += 1;
				return ["key", true];
			},
		});
		expect(() =>
			deserialize([5, ["$", "m", mapEntries]] as any),
		).toThrow("Malformed wire array at $[0]");
		expect(structuralAccessorCalls).toBe(0);
	});

	it("stays stable across the JSON boundary for seeded portable-domain graphs", () => {
		for (let seed = 1; seed <= 300; seed += 1) {
			const data = randomPortableValue(seededRandom(seed), 4);
			const wire = wireSerialize(data);
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
