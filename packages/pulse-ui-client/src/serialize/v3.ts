export type Primitive = number | string | boolean | null | undefined;
export type JSON<T> = T | Array<JSON<T>> | { [K: string]: JSON<T> };
export type PlainJSON = JSON<Primitive>;
export type Serializable = any;

export type Serialized = [
  [refs: string[], dates: string[], sets: string[], maps: string[]],
  PlainJSON,
];

export type Extension<T = unknown, R = unknown> = {
  check(value: unknown): value is T;
  encode(value: T, encode: (value: unknown) => number): R;
  decode(entry: R, decode: (index: number) => unknown): T;
};

export function extension<T, R = unknown>(ext: Extension<T, R>) {
  return ext;
}

export function serialize(data: Serializable): Serialized {
  // Keep track of potentially recursive objects (arrays and records)
  const seen = new Map<any, string>();
  const refs: string[] = [];
  const dates: string[] = [];
  const sets: string[] = [];
  const maps: string[] = [];

  function process(value: Serializable, path: string): PlainJSON {
    if (
      value == null || // catch both null and undefined
      typeof value === "number" ||
      typeof value === "string" ||
      typeof value === "boolean"
    ) {
      return value;
    }
    const prevRef = seen.get(value);
    if (prevRef !== undefined) {
      refs.push(path);
      return prevRef;
    }

    // Dates, arrays, and objects are all references, whose identity should be preserved
    seen.set(value, path);
    // Dates
    if (value instanceof Date) {
      dates.push(path);
      return value.getTime();
    }

    // Arrays
    if (Array.isArray(value)) {
      const result = [];
      for (let i = 0; i < value.length; i++) {
        result.push(process(value[i], path + "." + String(i)));
      }
      return result;
    }
    // Maps -> convert to record
    if (value instanceof Map) {
      maps.push(path);
      const rec: Record<string, any> = {};
      for (const [key, entry] of value.entries()) {
        rec[key] = process(entry, path + "." + key);
      }
      return rec;
    }

    // Sets -> convert to array
    if (value instanceof Set) {
      sets.push(path);
      const result = [];
      let i = 0;
      for (const entry of value) {
        result.push(process(entry, path + "." + String(i)));
        i += 1;
      }
      return result;
    }
    // plain object
    if (typeof value === "object") {
      const rec: Record<string, any> = {};
      for (const key of Object.keys(value)) {
        rec[key] = process(value[key], path + "." + key);
      }
      return rec;
    }

    throw new Error(`Unsupported value in serialization: ${value}`);
  }

  const payload = process(data, "");
  return [[refs, dates, sets, maps], payload];
}

export interface DeserializationOptions {
  coerceNullsToUndefined?: boolean;
}

export function deserialize<Data extends Serializable = Serializable>(
  payload: Serialized,
  options?: DeserializationOptions
): Data {
  const [[refs, dates, sets, maps], data] = payload;

  // Maps to store reconstructed objects and their paths
  const objects = new Map<string, any>();

  function reconstruct(value: PlainJSON, path: string): any {
    // Perform custom checks BEFORE primitives, as dates and circular references
    // are encoded as numbers and strings, respectively.

    // Check if this path refers to a previously created object (circular
    // reference)
    if (refs.includes(path)) {
      return objects.get(value as string);
    }

    // Check if this path should be a Date.
    if (dates.includes(path)) {
      const dt = new Date(value as number);
      objects.set(path, dt);
      return dt;
    }

    // Handle primitives
    if (
      value == null ||
      typeof value === "number" ||
      typeof value === "string" ||
      typeof value === "boolean"
    ) {
      if (options?.coerceNullsToUndefined) {
        return value ?? undefined;
      }
      return value;
    }

    // Handle arrays & sets
    if (Array.isArray(value)) {
      // Sets special case
      if (sets.includes(path)) {
        const result = new Set();
        objects.set(path, result);
        for (let i = 0; i < value.length; i++) {
          result.add(reconstruct(value[i], path + "." + String(i)));
        }
        return result;
      }
      // Arrays regular path
      const result: any[] = [];
      objects.set(path, result);
      for (let i = 0; i < value.length; i++) {
        result[i] = reconstruct(value[i], path + "." + String(i));
      }
      return result;
    }

    // Handle objects and maps
    if (typeof value === "object") {
      // Maps special case
      if (maps.includes(path)) {
        const result = new Map<string, any>();
        objects.set(path, result);
        for (const key of Object.keys(value)) {
          result.set(key, reconstruct(value[key], path + "." + key));
        }
        return result;
      }
      // Plain object regular path
      const result: Record<string, any> = {};
      objects.set(path, result);
      for (const key of Object.keys(value)) {
        result[key] = reconstruct(value[key], path + "." + key);
      }
      return result;
    }

    throw new Error(`Unsupported value in deserialization: ${value}`);
  }

  return reconstruct(data, "");
}
