import { describe, it, expect } from "vitest";
import {
  serialize as serialize,
  deserialize as deserialize,
} from "./serializer";

describe("v3 serialization", () => {
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

  it("throws on unsupported values (function/symbol)", () => {
    expect(() => serialize({ x: () => {} } as any)).toThrow();
    expect(() => serialize({ x: Symbol("s") } as any)).toThrow();
  });
});
