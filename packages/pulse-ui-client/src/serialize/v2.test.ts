import { describe, it, expect } from "vitest";
import { serialize, deserialize, type Extension } from "./v2";

// Date extension using encode/decode helpers
const DateExtension = {
  check(value: unknown): value is Date {
    return value instanceof Date;
  },
  encode(value: Date, encode: (v: unknown) => number) {
    return { t: encode("date"), ts: encode(value.getTime()) } as const;
  },
  decode(entry: any, decode: (i: number) => unknown): Date {
    const t = decode(entry.t) as string;
    if (t !== "date") throw new Error("Invalid date payload");
    const ts = decode(entry.ts) as number;
    return new Date(ts);
  },
} satisfies Extension<Date>;

describe("v2 serialization format", () => {
  it("serializes primitives as direct entries and round trips", () => {
    const data = [1, "a", true, null, undefined];
    const ser = serialize(data, []);
    const parsed = deserialize(ser, []);
    // null should be deserialized to undefined
    const expected = data.map(x => x ?? undefined)
    expect(parsed).toEqual(expected);
  });

  it("decodes nested extension values (Set of Dates) and preserves shared refs", () => {
    const d = new Date("2024-02-02T00:00:00Z");
    const SetExtension = {
      check(value: unknown): value is Set<unknown> {
        return value instanceof Set;
      },
      encode(value: Set<unknown>, encode: (v: unknown) => number) {
        return { t: encode("set"), items: encode(Array.from(value)) } as const;
      },
      decode(entry: any, decode: (i: number) => unknown) {
        const t = decode(entry.t) as string;
        if (t !== "set") throw new Error("Invalid set payload");
        const items = decode(entry.items) as unknown[];
        return new Set(items);
      },
    };

    const s = new Set([d, d]); // Set dedupes same ref -> size 1
    const data: any = { s, also: s, arr: [s, d] };

    const ser = serialize(data, [DateExtension, SetExtension]);
    const parsed: any = deserialize(ser, [DateExtension, SetExtension]);

    // Structure
    expect(parsed.s).toBeInstanceOf(Set);
    const items = Array.from(parsed.s.values());
    expect(items).toHaveLength(1);
    expect(items[0]).toBeInstanceOf(Date);
    expect(parsed.also).toBe(parsed.s); // shared Set reference
    expect(parsed.arr[0]).toBe(parsed.s); // shared Set
    expect(parsed.arr[1]).toBe(items[0]); // shared Date instance
  });

  it("handles cycles when extensions are present", () => {
    const d = new Date("2024-03-03T00:00:00Z");
    const root: any = { when: d };
    root.self = root;
    const ser = serialize(root, [DateExtension]);
    const parsed: any = deserialize(ser, [DateExtension]);

    expect(parsed.self).toBe(parsed);
    expect(parsed.when).toBeInstanceOf(Date);
    expect(parsed.when.getTime()).toBe(d.getTime());
  });

  it("supports multiple different extensions in one structure", () => {
    const d1 = new Date("2020-01-01T00:00:00Z");
    const d2 = new Date("2030-01-01T00:00:00Z");
    const SetExtension = {
      check(value: unknown): value is Set<unknown> {
        return value instanceof Set;
      },
      encode(value: Set<unknown>, encode: (v: unknown) => number) {
        return { t: encode("set"), items: encode(Array.from(value)) } as const;
      },
      decode(entry: any, decode: (i: number) => unknown) {
        const t = decode(entry.t) as string;
        if (t !== "set") throw new Error("Invalid set payload");
        const items = decode(entry.items) as unknown[];
        return new Set(items);
      },
    };
    const data: any = {
      list: [new Set([d1]), { deep: [new Set([d2, d1])] }],
      single: d2,
    };

    const ser = serialize(data, [DateExtension, SetExtension]);
    const parsed: any = deserialize(ser, [DateExtension, SetExtension]);

    expect(parsed.list[0]).toBeInstanceOf(Set);
    const firstSet = Array.from(parsed.list[0].values());
    expect(firstSet[0]).toBeInstanceOf(Date);
    expect(parsed.list[1].deep[0]).toBeInstanceOf(Set);
    const deepSet = Array.from(parsed.list[1].deep[0].values());
    expect(deepSet[0]).toBeInstanceOf(Date);
    expect(deepSet[1]).toBeInstanceOf(Date);
    expect(parsed.single).toBeInstanceOf(Date);
  });

  it("handles arrays and objects", () => {
    const data: any = { a: 1, b: [2, 3, { c: "x" }] };
    const ser = serialize(data, []);
    const parsed = deserialize(ser, []);
    expect(parsed).toEqual(data);
  });

  it("preserves cycles and shared references", () => {
    const shared: any = { v: 42 };
    const root: any = { left: { shared }, right: { shared } };
    root.self = root;

    const ser = serialize(root, []);
    const parsed: any = deserialize(ser, []);

    expect(parsed.left.shared).toBe(parsed.right.shared);
    expect(parsed.self).toBe(parsed);
    expect(parsed.left.shared.v).toBe(42);
  });

  it("uses extensions to decode marked indices (Date)", () => {
    const d = new Date("2024-01-01T00:00:00Z");
    const data = { when: d, same: d } as const;
    const ser = serialize(data, [DateExtension]);

    // expected: ext index list for the single extension includes the indices
    const [exts, entries] = ser;
    expect(exts).toHaveLength(1);
    expect(exts[0].length).toBeGreaterThan(0);
    // round trip
    const parsed: any = deserialize(ser, [DateExtension]);
    expect(parsed.when).toBeInstanceOf(Date);
    expect(parsed.when.getTime()).toBe(d.getTime());
    // shared reference must be preserved at same indices
    expect(parsed.when).toBe(parsed.same);
  });

  it("throws on unsupported values (function/symbol)", () => {
    expect(() => serialize({ x: () => {} } as any, [])).toThrow();
    expect(() => serialize({ x: Symbol("s") } as any, [])).toThrow();
  });
});
