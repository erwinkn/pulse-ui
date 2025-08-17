// Serialization helpers that support:
// - Circular references via object identity refs
// - Date instances → { __t: "datetime", timestamp }
// - FormData → { __t: "formdata", fields }
// - File → { __t: "file", name, type, size, lastModified, content: number[] }
// Along with a decoder for the symmetric shapes (we do not reconstruct File/FormData objects).

type EncodedRef = { __t: "ref"; id: number };
type EncodedArray = { __t: "array"; __id: number; items: unknown[] };
type EncodedObject = {
  __t: "object";
  __id: number;
  props: Record<string, unknown>;
};
type EncodedDate = { __t: "datetime"; timestamp: number };
type EncodedFile = {
  __t: "file";
  name: string;
  type: string;
  size: number;
  lastModified: number;
  content: number[]; // raw bytes as a JSON-safe number array
};
type EncodedFormData = {
  __t: "formdata";
  fields: Record<string, unknown | unknown[]>;
};

type IdentityMap = WeakMap<object, number>;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object") return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}


function isDate(value: unknown): value is Date {
  return value instanceof Date;
}

function isSkippable(value: unknown): boolean {
  return (
    typeof value === "function" ||
    typeof value === "symbol" ||
    typeof value === "undefined"
  );
}

async function fileToByteArray(file: File): Promise<number[]> {
  const ab = await file.arrayBuffer();
  return Array.from(new Uint8Array(ab));
}

interface EncodeContext {
  seen: IdentityMap;
  nextId: number;
}

export async function encodeForWire(input: unknown): Promise<unknown> {
  const ctx: EncodeContext = { seen: new WeakMap(), nextId: 1 };
  return await encodeRecursive(input, ctx);
}

function remember(ctx: EncodeContext, obj: object): number | null {
  const existing = ctx.seen.get(obj);
  if (existing !== undefined) return null;
  const id = ctx.nextId++;
  ctx.seen.set(obj, id);
  return id;
}

async function encodeRecursive(
  value: unknown,
  ctx: EncodeContext
): Promise<unknown> {
  if (value === null || typeof value !== "object") {
    return value;
  }

  // Special cases first
  if (value instanceof Date) {
    const date = value as Date;
    const encoded: EncodedDate = { __t: "datetime", timestamp: date.getTime() };
    return encoded;
  }

  if (value instanceof FormData) {
    const id = remember(ctx, value);
    if (id === null) {
      return { __t: "ref", id: ctx.seen.get(value as object)! } as EncodedRef;
    }
    const fields: Record<string, unknown | unknown[]> = {};
    for (const [key, v] of value.entries()) {
      const encodedVal = await encodeRecursive(v as unknown, ctx);
      if (encodedVal === undefined) continue;
      if (Object.prototype.hasOwnProperty.call(fields, key)) {
        const existing = fields[key];
        if (Array.isArray(existing)) {
          existing.push(encodedVal);
        } else {
          fields[key] = [existing, encodedVal];
        }
      } else {
        fields[key] = encodedVal;
      }
    }
    const encoded: EncodedFormData & { __id: number } = {
      __t: "formdata",
      fields,
      __id: id,
    } as any;
    return encoded;
  }

  if (value instanceof File) {
    const file = value;
    const bytes = await fileToByteArray(value);
    const encoded: EncodedFile = {
      __t: "file",
      name: file.name,
      type: file.type,
      size: file.size,
      lastModified: file.lastModified,
      content: bytes,
    };
    return encoded;
  }

  // Identity / circular reference handling
  const object = value as object;
  const existingId = ctx.seen.get(object);
  if (existingId !== undefined) {
    const ref: EncodedRef = { __t: "ref", id: existingId };
    return ref;
  }
  const thisId = ctx.nextId++;
  ctx.seen.set(object, thisId);

  if (Array.isArray(value)) {
    const itemsRaw = await Promise.all(
      (value as unknown[]).map((item) => encodeRecursive(item, ctx))
    );
    const items = itemsRaw.filter((it) => it !== undefined) as unknown[];
    const encoded: EncodedArray = { __t: "array", __id: thisId, items };
    return encoded;
  }

  // Plain object or other object types
  const props: Record<string, unknown> = {};
  if (isPlainObject(value)) {
    for (const key of Object.keys(value)) {
      const v = (value as Record<string, unknown>)[key];
      if (isSkippable(v)) continue;
      const encodedV = await encodeRecursive(v, ctx);
      if (encodedV !== undefined) props[key] = encodedV;
    }
  } else {
    // Non-plain objects: best effort – enumerate enumerable properties
    for (const key in value as Record<string, unknown>) {
      const v = (value as Record<string, unknown>)[key];
      if (isSkippable(v)) continue;
      const encodedV = await encodeRecursive(v, ctx);
      if (encodedV !== undefined) props[key] = encodedV;
    }
  }
  const encoded: EncodedObject = { __t: "object", __id: thisId, props };
  return encoded;
}

export function decodeFromWire(input: unknown): unknown {
  return decodeRecursive(input);
}

function decodeRecursive(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;

  const obj = value as Record<string, unknown>;
  const tag = obj["__t"];

  if (tag === "datetime") {
    const ts = obj["timestamp"] as number;
    return new Date(ts);
  }

  if (tag === "file") {
    // Do not reconstruct File; keep as plain object. Optionally, turn content into Uint8Array for convenience.
    const content = obj["content"];
    if (Array.isArray(content)) {
      // Return a shallow clone with Uint8Array for content
      return {
        ...obj,
        content: new Uint8Array(content as number[]),
      } as any;
    }
    return obj;
  }

  if (tag === "formdata") {
    // Keep as-is (plain object), but decode nested values
    const fields = obj["fields"] as Record<string, unknown | unknown[]>;
    const decodedFields: Record<string, unknown | unknown[]> = {};
    for (const key of Object.keys(fields)) {
      const v = fields[key];
      if (Array.isArray(v)) {
        decodedFields[key] = v.map((x) => decodeRecursive(x));
      } else {
        decodedFields[key] = decodeRecursive(v);
      }
    }
    return { __t: "formdata", fields: decodedFields } as EncodedFormData;
  }

  if (tag === "array") {
    const items = (obj["items"] as unknown[]).map((x) => decodeRecursive(x));
    return items;
  }

  if (tag === "object") {
    const props = obj["props"] as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(props)) {
      out[key] = decodeRecursive(props[key]);
    }
    return out;
  }

  if (tag === "ref") {
    // Without a reconstruction context on the client, leave as-is.
    return obj;
  }

  // Unknown object – descend shallowly
  const copy: Record<string, unknown> = {};
  for (const key of Object.keys(obj)) {
    copy[key] = decodeRecursive(obj[key]);
  }
  return copy;
}

// Legacy cleaner kept for compatibility where a quick best-effort JSON-safe shape is needed
export function cleanForSerialization(obj: unknown): unknown {
  return cleanRecursive(obj, new WeakSet());
}

function cleanRecursive(obj: unknown, seen: WeakSet<object>): unknown {
  if (obj === null || typeof obj !== "object") return obj;
  if (seen.has(obj as object)) return undefined;
  seen.add(obj as object);
  if (Array.isArray(obj)) {
    return (obj as unknown[])
      .map((item) => cleanRecursive(item, seen))
      .filter((x) => x !== undefined);
  }
  const out: Record<string, unknown> = {};
  for (const key in obj as Record<string, unknown>) {
    const v = (obj as Record<string, unknown>)[key];
    if (isSkippable(v)) continue;
    const cleaned = cleanRecursive(v, seen);
    if (cleaned !== undefined) out[key] = cleaned;
  }
  return out;
}
