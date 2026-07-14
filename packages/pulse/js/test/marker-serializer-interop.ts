import {
	DateOnly,
	deserialize,
	type Serialized,
	serialize,
} from "../src/serialize/marker-serializer";

type Descriptor =
	| { t: "null" }
	| { t: "bool"; value: boolean }
	| { t: "number"; value: number }
	| { t: "string"; value: string }
	| { t: "date"; id?: string; value: string }
	| { t: "datetime"; id?: string; value: string }
	| { t: "array"; id?: string; items: Descriptor[] }
	| { t: "record"; id?: string; entries: [string, Descriptor][] }
	| { t: "map"; id?: string; entries: [string, Descriptor][] }
	| { t: "set"; id?: string; items: Descriptor[] }
	| { t: "ref"; id: string };

type Request =
	| { op: "encode"; cases: Descriptor[] }
	| { op: "transcode"; wires: Serialized[] }
	| { op: "reject"; wires: unknown[] };

function materialize(
	descriptor: Descriptor,
	objects = new Map<string, unknown>(),
): unknown {
	switch (descriptor.t) {
		case "null":
			return null;
		case "bool":
		case "number":
		case "string":
			return descriptor.value;
		case "date": {
			const result = new DateOnly(descriptor.value);
			if (descriptor.id) objects.set(descriptor.id, result);
			return result;
		}
		case "datetime": {
			const result = new Date(descriptor.value);
			if (descriptor.id) objects.set(descriptor.id, result);
			return result;
		}
		case "ref": {
			if (!objects.has(descriptor.id)) {
				throw new Error(`Unknown descriptor reference: ${descriptor.id}`);
			}
			return objects.get(descriptor.id);
		}
		case "array": {
			const result: unknown[] = [];
			if (descriptor.id) objects.set(descriptor.id, result);
			for (const item of descriptor.items)
				result.push(materialize(item, objects));
			return result;
		}
		case "record": {
			const result: Record<string, unknown> = {};
			if (descriptor.id) objects.set(descriptor.id, result);
			for (const [key, value] of descriptor.entries) {
				const decoded = materialize(value, objects);
				if (key === "__proto__") {
					Object.defineProperty(result, key, {
						value: decoded,
						enumerable: true,
						configurable: true,
						writable: true,
					});
				} else {
					result[key] = decoded;
				}
			}
			return result;
		}
		case "map": {
			const result = new Map<string, unknown>();
			if (descriptor.id) objects.set(descriptor.id, result);
			for (const [key, value] of descriptor.entries) {
				result.set(key, materialize(value, objects));
			}
			return result;
		}
		case "set": {
			const result = new Set<unknown>();
			if (descriptor.id) objects.set(descriptor.id, result);
			for (const item of descriptor.items)
				result.add(materialize(item, objects));
			return result;
		}
	}
}

function snapshot(value: unknown, seen = new Map<object, number>()): unknown {
	if (value === null) return ["null"];
	if (typeof value === "boolean") return ["bool", value];
	if (typeof value === "number") return ["number", value];
	if (typeof value === "string") return ["string", value];
	if (value instanceof DateOnly) return ["date", String(value)];
	if (value instanceof Date) return ["datetime", value.toISOString()];
	if (typeof value !== "object")
		throw new Error(`Unsupported snapshot value: ${typeof value}`);

	const previous = seen.get(value);
	if (previous !== undefined) return ["ref", previous];
	const id = seen.size;
	seen.set(value, id);

	if (Array.isArray(value)) {
		return ["array", id, value.map((item) => snapshot(item, seen))];
	}
	if (value instanceof Map) {
		return [
			"map",
			id,
			[...value].map(([key, item]) => [key, snapshot(item, seen)]),
		];
	}
	if (value instanceof Set) {
		const items = [...value].map((item) => snapshot(item, seen));
		items.sort((left, right) =>
			JSON.stringify(left).localeCompare(JSON.stringify(right)),
		);
		return ["set", id, items];
	}

	const record = value as Record<string, unknown>;
	const entries = Object.keys(record)
		.sort()
		.map((key) => [key, snapshot(record[key], seen)]);
	return ["record", id, entries];
}

function crossJSON<Data>(value: Data): Data {
	return JSON.parse(JSON.stringify(value));
}

const request = JSON.parse(await Bun.stdin.text()) as Request;
if (request.op === "encode") {
	const results = request.cases.map((descriptor) => {
		const value = materialize(descriptor);
		const wire = crossJSON(serialize(value));
		return {
			wire,
			snapshot: snapshot(value),
			decodedSnapshot: snapshot(deserialize(wire)),
		};
	});
	process.stdout.write(JSON.stringify(results));
} else if (request.op === "transcode") {
	const results = request.wires.map((input) => {
		const value = deserialize(input);
		return {
			snapshot: snapshot(value),
			wire: crossJSON(serialize(value)),
		};
	});
	process.stdout.write(JSON.stringify(results));
} else {
	const results = request.wires.map((input) => {
		try {
			deserialize(input as Serialized);
			return false;
		} catch {
			return true;
		}
	});
	process.stdout.write(JSON.stringify(results));
}
