export type Primitive = number | string | boolean | null | undefined;
export type JSON<T> = T | Array<JSON<T>> | { [K: string]: JSON<T> };
export type PlainJSON = JSON<Primitive>;
export type Serializable = any;

export type Serialized = [[number[], number[], number[], number[]], PlainJSON];

function isDomNode(value: object): boolean {
	if (typeof Node !== "undefined" && value instanceof Node) {
		return true;
	}
	for (
		let prototype = Object.getPrototypeOf(value);
		prototype !== null && prototype !== Object.prototype;
		prototype = Object.getPrototypeOf(prototype)
	) {
		const tag = Object.getOwnPropertyDescriptor(prototype, Symbol.toStringTag);
		if (
			tag?.value === "Node" &&
			typeof Object.getOwnPropertyDescriptor(prototype, "nodeType")?.get === "function" &&
			typeof Object.getOwnPropertyDescriptor(prototype, "nodeName")?.get === "function" &&
			typeof Object.getOwnPropertyDescriptor(prototype, "ownerDocument")?.get === "function" &&
			typeof Object.getOwnPropertyDescriptor(prototype, "cloneNode")?.value === "function"
		) {
			return true;
		}
	}
	return false;
}

const REACT_FIBER_KEYS = [
	"tag",
	"key",
	"elementType",
	"type",
	"stateNode",
	"return",
	"child",
	"sibling",
	"index",
	"ref",
	"pendingProps",
	"memoizedProps",
	"updateQueue",
	"memoizedState",
	"dependencies",
	"mode",
	"flags",
	"subtreeFlags",
	"deletions",
	"lanes",
	"childLanes",
	"alternate",
] as const;

const CHECK_REACT_FIBER =
	import.meta.env?.DEV ??
	(typeof process !== "undefined" && process.env.NODE_ENV !== "production");

function isReactFiber(value: object): boolean {
	const candidate = value as Record<string, unknown>;
	if (!REACT_FIBER_KEYS.every((key) => Object.hasOwn(candidate, key))) {
		return false;
	}
	if (
		typeof candidate.tag !== "number" ||
		typeof candidate.index !== "number" ||
		typeof candidate.mode !== "number" ||
		typeof candidate.flags !== "number" ||
		typeof candidate.subtreeFlags !== "number" ||
		typeof candidate.lanes !== "number" ||
		typeof candidate.childLanes !== "number"
	) {
		return false;
	}
	return true;
}

export function serialize(data: Serializable): Serialized {
	const seen = new Map<any, number>();
	const refs: number[] = [];
	const dates: number[] = [];
	const sets: number[] = [];
	const maps: number[] = [];

	// Single global counter - increments once per payload node visit
	let globalIndex = 0;

	function process(value: Serializable, context?: string): PlainJSON {
		const idx = globalIndex++;

		if (value == null || typeof value === "string" || typeof value === "boolean") {
			return value;
		}

		if (typeof value === "number") {
			if (Number.isNaN(value)) {
				return null;
			}
			if (!Number.isFinite(value)) {
				const kind = value > 0 ? "Infinity" : "-Infinity";
				const ctx = context ? ` in '${context}'` : "";
				throw new Error(
					`Cannot serialize ${kind}${ctx}. NaN and Infinity are not supported because they cannot be serialized to JSON.`,
				);
			}
			return value;
		}

		// Functions and symbols cannot cross the wire. Rather than crash the whole
		// payload, coerce them to null — exactly like NaN above. A common real-world
		// source is a React element ($$typeof is a symbol) leaking into a callback arg;
		// one stray element shouldn't nuke an entire form submission. `idx` was already
		// consumed at the top of `process`, so the dropped leaf behaves like any other
		// primitive and the ref/date/set/map indices stay aligned with `deserialize`.
		if (typeof value === "function" || typeof value === "symbol") {
			return null;
		}

		if (typeof value === "object") {
			const ctx = context ? ` in '${context}'` : "";
			if (isDomNode(value)) {
				throw new Error(
					`Cannot serialize a DOM node${ctx}. Extract DOM events/elements before serializing.`,
				);
			}
			// A raw DOM node is always invalid serializer input, including in production.
			// Fiber has no public brand, so keep its heuristic diagnostic out of the hot
			// production path; DOM nodes are rejected before their expandos are traversed.
			if (CHECK_REACT_FIBER && isReactFiber(value)) {
				throw new Error(
					`Cannot serialize a React Fiber${ctx}. Extract DOM events/elements before serializing.`,
				);
			}
		}

		const prevRef = seen.get(value);
		if (prevRef !== undefined) {
			// Make sure to push the current index, but use the ref's index as the value!
			refs.push(idx);
			return prevRef;
		}

		seen.set(value, idx);

		if (value instanceof Date) {
			dates.push(idx);
			return value.toISOString();
		}

		if (Array.isArray(value)) {
			const length = value.length;
			const result = new Array(length);
			for (let i = 0; i < length; i++) {
				result[i] = process(value[i], context);
			}
			return result;
		}

		if (value instanceof Map) {
			maps.push(idx);
			const rec: Record<string, any> = {};
			for (const [key, entry] of value.entries()) {
				rec[String(key)] = process(entry, String(key));
			}
			return rec;
		}

		if (value instanceof Set) {
			sets.push(idx);
			const size = value.size;
			const result = new Array(size);
			let i = 0;
			for (const entry of value) {
				result[i] = process(entry, context);
				i += 1;
			}
			return result;
		}

		if (typeof value === "object") {
			const rec: Record<string, any> = {};
			const keys = Object.keys(value);
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				rec[key] = process(value[key], key);
			}
			return rec;
		}

		// Reachable only for genuinely unsupported types that carry real data the
		// caller likely intended to send (e.g. bigint) — unlike functions/symbols, we
		// don't silently drop these. Build the message from `typeof`, never from `value`
		// itself: interpolating a symbol here would throw "Cannot convert a symbol to a
		// string", masking both the real error and the `context` path.
		const where = context ? ` in '${context}'` : "";
		throw new Error(
			`Cannot serialize value of type '${typeof value}'${where}. ` +
				`Only JSON-compatible values (plus Date, Map, and Set) can be sent over the wire.`,
		);
	}

	const payload = process(data);
	return [[refs, dates, sets, maps], payload];
}

export interface DeserializationOptions {
	coerceNullsToUndefined?: boolean;
}

export function deserialize<Data extends Serializable = Serializable>(
	payload: Serialized,
	options?: DeserializationOptions,
): Data {
	const [[refsA, datesA, setsA, mapsA], data] = payload;

	const refs = new Set(refsA);
	const dates = new Set(datesA);
	const sets = new Set(setsA);
	const maps = new Set(mapsA);

	const objects = new Map<number, any>();
	let globalIndex = 0;

	function reconstruct(value: PlainJSON): any {
		const idx = globalIndex++;
		if (refs.has(idx)) {
			if (typeof value !== "number") {
				throw new Error("Reference payload must be a numeric index");
			}
			if (!objects.has(value)) {
				throw new Error(`Dangling reference to index ${value}`);
			}
			return objects.get(value);
		}

		if (dates.has(idx)) {
			if (typeof value !== "string") {
				throw new Error("Date payload must be an ISO string");
			}
			const literal = parseDateLiteral(value);
			if (literal) {
				const [y, m, d] = literal;
				const dt = new Date(Date.UTC(y, m - 1, d));
				objects.set(idx, dt);
				return dt;
			}
			if (isDateLiteral(value)) {
				throw new Error(`Invalid date literal: ${value}`);
			}
			const dt = new Date(value);
			objects.set(idx, dt);
			return dt;
		}

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

		if (Array.isArray(value)) {
			if (sets.has(idx)) {
				const result = new Set();
				objects.set(idx, result);
				for (let i = 0; i < value.length; i++) {
					result.add(reconstruct(value[i]));
				}
				return result;
			}

			const length = value.length;
			const arr = new Array(length);
			objects.set(idx, arr);
			for (let i = 0; i < length; i++) {
				arr[i] = reconstruct(value[i]);
			}
			return arr;
		}

		if (typeof value === "object") {
			if (maps.has(idx)) {
				const result = new Map<string, any>();
				objects.set(idx, result);
				const keys = Object.keys(value);
				for (let i = 0; i < keys.length; i++) {
					const key = keys[i];
					result.set(key, reconstruct(value[key]));
				}
				return result;
			}

			const result: Record<string, any> = {};
			objects.set(idx, result);
			const keys = Object.keys(value);
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				result[key] = reconstruct(value[key]);
			}
			return result;
		}

		throw new Error(`Unsupported value in deserialization: ${value}`);
	}

	return reconstruct(data);
}

const DATE_LITERAL_RE = /^\d{4}-\d{2}-\d{2}$/;

function isDateLiteral(value: string): boolean {
	return DATE_LITERAL_RE.test(value);
}

function parseDateLiteral(value: string): [number, number, number] | null {
	if (!isDateLiteral(value)) {
		return null;
	}
	const [yStr, mStr, dStr] = value.split("-");
	const y = Number(yStr);
	const m = Number(mStr);
	const d = Number(dStr);
	if (!Number.isInteger(y) || !Number.isInteger(m) || !Number.isInteger(d)) {
		return null;
	}
	if (m < 1 || m > 12 || d < 1 || d > 31) {
		return null;
	}
	const dt = new Date(Date.UTC(y, m - 1, d));
	if (
		dt.getUTCFullYear() !== y ||
		dt.getUTCMonth() !== m - 1 ||
		dt.getUTCDate() !== d
	) {
		return null;
	}
	return [y, m, d];
}
