/* -- Data format --  
Serialized data consists of:
1) A first array containing one entry per extension provided during
   serialization. For each extension, an array of indices is provided. These
   indices refer to the entries in the second array that were serialized using
   this extension. These entries should be deserialized by their corresponding
   extension. 
2) A second array containing the data entries. Each entry can be:
  - A primitive (number, string, boolean).
  - A record whose keys are strings and whose values are indices into the data
    entries array.
  - An array whose values are indices into the data entries array.

Extensions need to encode their inputs into plain JSON. The entries marked for
decoding by an extension will first reconstruct the plain JSON from the
corresponding data entry, before handing it off to the extension.

This format is similar to the one adopted by Flatted, but with a different
extension system.
*/
export type Primitive = number | string | boolean;
export type DataEntry = Primitive | Record<string, number> | Array<number>;
export type Serialized = [Array<Array<number>>, Array<DataEntry>];

export type Extension<T = unknown> = {
  check(value: unknown): value is T;
  encode(value: T, encode: (value: unknown) => number): DataEntry;
  decode(entry: DataEntry, decode: (index: number) => unknown): T;
};

type ExtensionType<E extends Extension<unknown>> =
  E extends Extension<infer T> ? T : never;
type ExtensionTypes<Extensions extends Array<Extension<unknown>>> =
  ExtensionType<Extensions[number]>;

export type PrimitiveWithExt<Ext extends unknown = never> = Primitive | Ext;
export type Serializable<Ext extends unknown = never> =
  | PrimitiveWithExt<Ext>
  | Array<PrimitiveWithExt<Ext>>
  | Record<string, PrimitiveWithExt<Ext>>;

export type SerializableWith<Extensions extends Array<Extension<any>>> = Serializable<
  ExtensionTypes<Extensions>
>;

export function serialize<Extensions extends Array<Extension>>(
  data: SerializableWith<Extensions>,
  extensions: Extensions
): Serialized {
  const entries: Array<DataEntry> = [];
  const extIdxLists: Array<Array<number>> = extensions.map(() => []);

  const seen = new Map<any, number>();

  const add = (value: any): number => {
    const cached = seen.get(value);
    if (cached !== undefined) return cached;
    // Primitives (as defined by this format) are stored directly
    if (
      typeof value === "number" ||
      typeof value === "string" ||
      typeof value === "boolean"
    ) {
      const idx = entries.length;
      entries.push(value as Primitive);
      seen.set(value, idx);
      return idx;
    }

    // Handle extension-encoded values
    for (let e = 0; e < extensions.length; e++) {
      const ext = extensions[e]!;
      if (ext.check(value)) {
        if (seen.has(value)) {
          return seen.get(value)!;
        }
        const idx = entries.length;
        // placeholder to support cycles while encoding children
        entries.push([]);
        seen.set(value, idx);
        const entry = ext.encode(value as any, (v: unknown) => add(v));
        entries[idx] = entry as DataEntry;
        extIdxLists[e]!.push(idx);
        return idx;
      }
    }

    // Non-primitive, non-extension values must be arrays or plain objects
    if (value && typeof value === "object") {
      if (seen.has(value)) {
        return seen.get(value)!;
      }

      if (Array.isArray(value)) {
        const idx = entries.length;
        // placeholder first to establish index for cycles
        entries.push([]);
        seen.set(value, idx);
        const childIndices: number[] = [];
        for (let i = 0; i < value.length; i++) {
          childIndices.push(add(value[i]));
        }
        entries[idx] = childIndices;
        return idx;
      }

      // plain object
      const idx = entries.length;
      entries.push({});
      seen.set(value, idx);
      const rec: Record<string, number> = {};
      for (const key of Object.keys(value)) {
        const v = (value as Record<string, any>)[key];
        const childIdx = add(v);
        rec[key] = childIdx as number;
      }
      entries[idx] = rec;
      return idx;
    }

    // Unsupported types (undefined, function, symbol, bigints, null)
    // Note: null is not part of Primitive in this v2 format. Skip it explicitly.
    throw new Error(
      `Unsupported value in serialize(): ${String(value)} (type ${typeof value})`
    );
  };

  // By convention, the root value is the first entry (index 0)
  add(data as any);

  return [extIdxLists, entries];
}

export function deserialize<Extensions extends Array<Extension>>(
  data: Serialized,
  extensions: Extensions
): SerializableWith<Extensions> {
  const [extIdxLists, entries] = data;

  // Map node index -> extension index responsible for decoding it
  const nodeToExt = new Map<number, number>();
  for (let e = 0; e < extIdxLists.length; e++) {
    for (const idx of extIdxLists[e] ?? []) {
      nodeToExt.set(idx, e);
    }
  }

  // Single resolver with extension-aware decode
  const resolved = new Map<number, any>();
  const resolve = (idx: number): any => {
    if (resolved.has(idx)) return resolved.get(idx);

    const entry = entries[idx];
    if (entry === undefined) {
      throw new Error(`Invalid serialized data: missing entry at index ${idx}`);
    }

    if (nodeToExt.has(idx)) {
      const ext = extensions[nodeToExt.get(idx)!]!;
      const value = ext.decode(entries[idx] as DataEntry, (j: number) =>
        resolve(j)
      );
      resolved.set(idx, value);
      return value;
    }

    if (
      typeof entry === "number" ||
      typeof entry === "string" ||
      typeof entry === "boolean"
    ) {
      resolved.set(idx, entry);
      return entry;
    }

    if (Array.isArray(entry)) {
      const arr: any[] = [];
      resolved.set(idx, arr);
      for (const childIndex of entry as number[]) {
        arr.push(resolve(childIndex));
      }
      return arr;
    }

    const obj: Record<string, any> = {};
    resolved.set(idx, obj);
    const map = entry as Record<string, number>;
    for (const k in map) {
      obj[k] = resolve(map[k] as number);
    }
    return obj;
  };

  if (entries.length === 0) {
    throw new Error("Invalid serialized data: empty entries array");
  }
  return resolve(0);
}
