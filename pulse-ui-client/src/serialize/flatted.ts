// Simple object transformation for socket.io transport
// Handles Dates, Files (via socket.io binary), FormData, and circular references

function isDate(value: unknown): value is Date {
  return value instanceof Date;
}

function isFile(value: unknown): value is File {
  return typeof File !== "undefined" && value instanceof File;
}

function isFormData(value: unknown): value is FormData {
  return typeof FormData !== "undefined" && value instanceof FormData;
}

export function stringify(input: unknown): unknown {
  const seen = new Map<object, number>();
  let nextId = 1;

  const transform = (value: unknown): unknown => {
    if (value === null || typeof value !== "object") {
      return value;
    }

    // Handle circular references
    const obj = value as object;
    if (seen.has(obj)) {
      return { __ref: seen.get(obj) };
    }

    // Special type transformations
    if (isDate(value)) {
      const id = nextId++;
      seen.set(obj, id);
      return { __pulse: "date", __id: id, timestamp: value.getTime() };
    }

    if (isFile(value)) {
      // Socket.io can handle File objects directly, just add metadata wrapper
      const id = nextId++;
      seen.set(obj, id);
      return {
        __pulse: "file",
        __id: id,
        name: value.name,
        type: value.type,
        size: value.size,
        lastModified: value.lastModified,
        file: value, // socket.io will handle the binary data
      };
    }

    if (isFormData(value)) {
      const id = nextId++;
      seen.set(obj, id);
      const fields: Record<string, unknown | unknown[]> = {};

      for (const [key, val] of value.entries()) {
        const transformedVal = transform(val);
        if (Object.prototype.hasOwnProperty.call(fields, key)) {
          const existing = fields[key];
          if (Array.isArray(existing)) {
            existing.push(transformedVal);
          } else {
            fields[key] = [existing, transformedVal];
          }
        } else {
          fields[key] = transformedVal;
        }
      }

      return { __pulse: "formdata", __id: id, fields };
    }

    // Regular objects and arrays
    const id = nextId++;
    seen.set(obj, id);

    if (Array.isArray(value)) {
      return {
        __pulse: "array",
        __id: id,
        items: value.map(transform),
      };
    }

    // Plain objects - use __pulse_data to avoid conflicts
    const userData: Record<string, unknown> = {};
    for (const key in value as Record<string, unknown>) {
      const v = (value as Record<string, unknown>)[key];
      if (
        typeof v === "function" ||
        typeof v === "symbol" ||
        typeof v === "undefined"
      ) {
        continue;
      }
      userData[key] = transform(v);
    }

    return { __pulse: "object", __id: id, __data: userData };
  };

  return transform(input);
}

export function parse(input: unknown): unknown {
  const objects = new Map<number, unknown>();

  const resolve = (value: unknown): unknown => {
    if (value === null || typeof value !== "object") {
      return value;
    }

    if (Array.isArray(value)) {
      return value.map(resolve);
    }

    const obj = value as Record<string, unknown>;

    // Handle references
    if (obj.__ref !== undefined) {
      const id = obj.__ref as number;
      return objects.get(id) || null;
    }

    // Handle special types (only if they have __pulse marker)
    if (obj.__pulse === "date") {
      const id = obj.__id as number;
      const resolved = new Date(obj.timestamp as number);
      objects.set(id, resolved);
      return resolved;
    }

    if (obj.__pulse === "file") {
      const id = obj.__id as number;
      // Return the original File object directly (socket.io preserves it)
      const resolved = obj.file as File;
      objects.set(id, resolved);
      return resolved;
    }

    if (obj.__pulse === "formdata") {
      const id = obj.__id as number;
      const fields = obj.fields as Record<string, unknown | unknown[]>;

      // Reconstruct FormData object
      const resolved = new FormData();
      objects.set(id, resolved);

      for (const [key, v] of Object.entries(fields)) {
        if (Array.isArray(v)) {
          // Multiple values for same key
          for (const item of v) {
            const resolvedItem = resolve(item);
            resolved.append(key, resolvedItem as string | File);
          }
        } else {
          const resolvedValue = resolve(v);
          resolved.append(key, resolvedValue as string | File);
        }
      }

      return resolved;
    }

    if (obj.__pulse === "array") {
      const id = obj.__id as number;
      const resolved: unknown[] = [];
      objects.set(id, resolved);

      const items = obj.items as unknown[];
      for (let i = 0; i < items.length; i++) {
        resolved[i] = resolve(items[i]);
      }
      return resolved;
    }

    if (obj.__pulse === "object") {
      const id = obj.__id as number;
      const resolved: Record<string, unknown> = {};
      objects.set(id, resolved);

      const userData = obj.__data as Record<string, unknown>;
      for (const [key, v] of Object.entries(userData)) {
        resolved[key] = resolve(v);
      }
      return resolved;
    }

    // Unknown object type - process properties
    const result: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(obj)) {
      result[key] = resolve(v);
    }
    return result;
  };

  return resolve(input);
}
