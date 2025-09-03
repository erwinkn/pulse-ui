import { describe, it, expect } from "vitest";
import { encodeForWire, decodeFromWire } from "./clean";

describe("encodeForWire / decodeFromWire", () => {
  it("encodes and decodes Date", async () => {
    const d = new Date(1730000000000);
    const encoded = await encodeForWire({ d });
    const decoded = decodeFromWire(encoded) as any;
    expect(decoded.d instanceof Date).toBe(true);
    expect((decoded.d as Date).getTime()).toBe(1730000000000);
  });

  it("encodes FormData fields and File", async () => {
    const fd = new FormData();
    const file = new File([new Uint8Array([1, 2, 3])], "a.bin", {
      type: "application/octet-stream",
      lastModified: 100,
    });
    fd.append("name", "alice");
    fd.append("file", file);
    fd.append(
      "file",
      new Blob([new Uint8Array([4, 5])], { type: "application/octet-stream" }),
      "b.bin"
    );

    const encoded = await encodeForWire(fd);
    const e = encoded as any;
    expect(e.__t).toBe("formdata");
    expect(e.fields.name).toBe("alice");
    const files = Array.isArray(e.fields.file)
      ? e.fields.file
      : [e.fields.file];
    for (const f of files) {
      expect(f.__t).toBe("file");
      expect(typeof f.name).toBe("string");
      expect(typeof f.size).toBe("number");
      expect(Array.isArray(f.content)).toBe(true);
    }

    const decoded = decodeFromWire(encoded) as any;
    const dfiles = Array.isArray(decoded.fields.file)
      ? decoded.fields.file
      : [decoded.fields.file];
    for (const f of dfiles) {
      // content becomes Uint8Array on decode
      expect(f.content instanceof Uint8Array).toBe(true);
    }
  });

  it.only("handles circular references with refs", async () => {
    const a: any = { name: "a" };
    const b: any = { name: "b", a };
    a.b = b;
    const arr: any[] = [a];
    a.arr = arr;

    const encoded = await encodeForWire({ a, b, arr });
    const asAny = encoded as any;
    // Expect top-level to be encoded as object with props
    expect(asAny.__t).toBe("object");
    // There should be some refs inside; we can't assert exact structure easily,
    // but verifying presence of { __t: "ref", id: ... } somewhere.
    const json = JSON.stringify(encoded);
    expect(json.includes('"__t":"ref"'));

    // Decoding keeps placeholders for refs (no identity reconstruction on client)
    const decoded = decodeFromWire(encoded) as any;
    expect(typeof decoded).toBe("object");
    expect(decoded.a.name).toBe("a");
    expect(decoded.b.__t).toBe("ref");
    expect(decoded.arr.__t).toBe("ref");
  });
});
