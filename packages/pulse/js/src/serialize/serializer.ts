export type Primitive = number | string | boolean | null;

export type WireValue = Primitive | WireValue[] | { [key: string]: WireValue };
export type Serialized = [5, WireValue];

const VERSION = 5;
const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;
const DATETIME_RE =
	/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z(?![\s\S])/;
const isWellFormed = String.prototype.isWellFormed;

type PathSegment = string | number;
type PortableSetValue = Primitive | Date;

interface CanonicalSetItem {
	value: PortableSetValue;
	rank: number;
	number: number;
	text: string;
	collisionKey: string;
}

export function serialize(data: unknown): Serialized {
	const seen = new Map<object, number>();
	const path: PathSegment[] = [];

	function encode(value: unknown): WireValue {
		if (value === null || value === undefined) {
			return null;
		}

		if (typeof value === "boolean") {
			return value;
		}
		if (typeof value === "string") {
			validateString(value, "serialize", path);
			return value;
		}
		if (typeof value === "number") {
			return encodeNumber(value, path);
		}
		const valueType = typeof value;
		if (valueType !== "object") {
			throw new TypeError(`Cannot serialize ${valueType} at ${formatPath(path)}`);
		}

		const object = value as object;
		const existingId = seen.get(object);
		if (existingId !== undefined) {
			return ["$", existingId];
		}
		seen.set(object, seen.size);

		if (value instanceof Date) {
			return ["$", "t", dateToWire(value, path)];
		}

		if (Array.isArray(value)) {
			const length = value.length;
			const items = new Array<WireValue>(length);
			for (let index = 0; index < length; index += 1) {
				path.push(index);
				items[index] = encode(value[index]);
				path.pop();
			}
			return items.length > 0 && items[0] === "$" ? ["$", "a", items] : items;
		}

		if (value instanceof Map) {
			const entries: [string, WireValue][] = [];
			const iterator = Map.prototype.entries.call(value) as IterableIterator<
				[unknown, unknown]
			>;
			let index = 0;
			for (const [rawKey, entry] of iterator) {
				if (typeof rawKey !== "string") {
					throw new TypeError(
						`Cannot serialize Map key of type ${typeof rawKey} at ${formatSetPath(path, "map", index)}`,
					);
				}
				validateString(rawKey, "serialize", path);
				path.push(rawKey);
				entries.push([rawKey, encode(entry)]);
				path.pop();
				index += 1;
			}
			return ["$", "m", entries];
		}

		if (value instanceof Set) {
			const items = canonicalizeSet(value, path);
			const encoded = new Array<WireValue>(items.length);
			for (let index = 0; index < items.length; index += 1) {
				path.push(`<set:${index}>`);
				encoded[index] = encode(items[index].value);
				path.pop();
			}
			return ["$", "s", encoded];
		}

		const prototype = Object.getPrototypeOf(value);
		if (prototype !== Object.prototype && prototype !== null) {
			throw new TypeError(
				`Cannot serialize object with prototype ${prototypeName(prototype)} at ${formatPath(path)}`,
			);
		}

		const result: Record<string, WireValue> = Object.create(null);
		const keys = Object.keys(value);
		for (let index = 0; index < keys.length; index += 1) {
			const key = keys[index];
			validateString(key, "serialize", path);
			const entry = (value as Record<string, unknown>)[key];
			if (entry === undefined) {
				continue;
			}
			path.push(key);
			result[key] = encode(entry);
			path.pop();
		}
		return result;
	}

	return [VERSION, encode(data)];
}

export function deserialize<Data = unknown>(payload: Serialized): Data {
	if (!Array.isArray(payload) || payload.length !== 2) {
		throw new TypeError("Wire payload must be [5, value]");
	}
	if (payload[0] !== VERSION) {
		throw new Error(`Unknown serialization version: ${String(payload[0])}`);
	}

	const identities: any[] = [];
	const path: PathSegment[] = [];

	function register<T>(value: T): T {
		identities.push(value);
		return value;
	}

	function decode(value: unknown): any {
		if (value === null || typeof value === "boolean") {
			return value;
		}
		if (typeof value === "string") {
			validateString(value, "deserialize", path);
			return value;
		}
		if (typeof value === "number") {
			return decodeNumber(value, path);
		}
		if (Array.isArray(value)) {
			if (value.length > 0 && value[0] === "$") {
				return decodeMarker(value);
			}
			const result = register(new Array(value.length));
			for (let index = 0; index < value.length; index += 1) {
				path.push(index);
				result[index] = decode(value[index]);
				path.pop();
			}
			return result;
		}
		if (typeof value !== "object" || value === null) {
			throw new TypeError(
				`Cannot deserialize wire value of type ${typeof value} at ${formatPath(path)}`,
			);
		}

		const prototype = Object.getPrototypeOf(value);
		if (prototype !== Object.prototype && prototype !== null) {
			throw new TypeError(`Malformed wire object at ${formatPath(path)}`);
		}
		const result = register({} as Record<string, any>);
		const keys = Object.keys(value);
		for (let index = 0; index < keys.length; index += 1) {
			const key = keys[index];
			validateString(key, "deserialize", path);
			path.push(key);
			const entry = decode((value as Record<string, unknown>)[key]);
			path.pop();
			defineRecordValue(result, key, entry);
		}
		return result;
	}

	function decodeMarker(marker: unknown[]): any {
		if (marker.length === 2 && typeof marker[1] === "number") {
			const identityId = decodeIdentityId(marker[1], path);
			if (identityId >= identities.length) {
				throw new Error(
					`Dangling reference to id ${identityId} at ${formatPath(path)}`,
				);
			}
			return identities[identityId];
		}

		if (marker.length < 2 || typeof marker[1] !== "string") {
			throw new Error(`Malformed marker at ${formatPath(path)}`);
		}
		const tag = marker[1];
		validateString(tag, "deserialize", path);

		if (tag === "a") {
			assertMarkerLength(marker, 3, path);
			const rawItems = marker[2];
			if (!Array.isArray(rawItems) || rawItems.length === 0 || rawItems[0] !== "$") {
				throw new Error(
					`Escaped array payload must begin with '$' at ${formatPath(path)}`,
				);
			}
			const result = register(new Array(rawItems.length));
			for (let index = 0; index < rawItems.length; index += 1) {
				path.push(index);
				result[index] = decode(rawItems[index]);
				path.pop();
			}
			return result;
		}

		if (tag === "t") {
			assertMarkerLength(marker, 3, path);
			if (typeof marker[2] !== "string") {
				throw new Error(`Datetime payload must be a string at ${formatPath(path)}`);
			}
			return register(dateFromWire(marker[2], path));
		}

		if (tag === "m") {
			assertMarkerLength(marker, 3, path);
			const rawEntries = marker[2];
			if (!Array.isArray(rawEntries)) {
				throw new Error(`Map payload must be an array at ${formatPath(path)}`);
			}
			const result = register(new Map<string, any>());
			const keys = new Set<string>();
			for (let index = 0; index < rawEntries.length; index += 1) {
				const rawEntry = rawEntries[index];
				if (
					!Array.isArray(rawEntry) ||
					rawEntry.length !== 2 ||
					typeof rawEntry[0] !== "string"
				) {
					throw new Error(
						`Map entry must be [string, value] at ${formatSetPath(path, "map", index)}`,
					);
				}
				const key = rawEntry[0];
				validateString(key, "deserialize", path);
				if (keys.has(key)) {
					throw new Error(
						`Duplicate Map key ${JSON.stringify(key)} at ${formatSetPath(path, "map", index)}`,
					);
				}
				keys.add(key);
				path.push(key);
				result.set(key, decode(rawEntry[1]));
				path.pop();
			}
			return result;
		}

		if (tag === "s") {
			assertMarkerLength(marker, 3, path);
			const rawItems = marker[2];
			if (!Array.isArray(rawItems)) {
				throw new Error(`Set payload must be an array at ${formatPath(path)}`);
			}
			const result = register(new Set<PortableSetValue>());
			const collisions = new Set<string>();
			let previous: CanonicalSetItem | undefined;
			for (let index = 0; index < rawItems.length; index += 1) {
				path.push(`<set:${index}>`);
				const value = decode(rawItems[index]);
				const item = describeDecodedSetValue(value, path);
				path.pop();
				if (previous !== undefined && compareSetItems(previous, item) > 0) {
					throw new Error(
						`Set entries are not canonically ordered at ${formatSetPath(path, "set", index)}`,
					);
				}
				if (collisions.has(item.collisionKey)) {
					throw new Error(
						`Duplicate or cross-runtime-colliding Set entry at ${formatSetPath(path, "set", index)}`,
					);
				}
				previous = item;
				collisions.add(item.collisionKey);
				result.add(item.value);
			}
			return result;
		}

		throw new Error(`Unknown marker tag ${JSON.stringify(tag)} at ${formatPath(path)}`);
	}

	return decode(payload[1]) as Data;
}

function encodeNumber(value: number, path: PathSegment[]): number | null {
	if (Number.isNaN(value)) {
		return null;
	}
	validateFiniteNumber(value, "serialize", path);
	if (Object.is(value, -0)) {
		throw new Error(`Cannot serialize negative zero at ${formatPath(path)}`);
	}
	return value;
}

function decodeNumber(value: number, path: PathSegment[]): number {
	validateFiniteNumber(value, "deserialize", path);
	return Object.is(value, -0) ? 0 : value;
}

function validateFiniteNumber(
	value: number,
	verb: "serialize" | "deserialize",
	path: PathSegment[],
): void {
	if (!Number.isFinite(value)) {
		throw new Error(`Cannot ${verb} non-finite number at ${formatPath(path)}`);
	}
	if (Number.isInteger(value) && Math.abs(value) > MAX_SAFE_INTEGER) {
		throw new Error(`Cannot ${verb} unsafe integer at ${formatPath(path)}`);
	}
}

function validateString(
	value: string,
	verb: "serialize" | "deserialize",
	path: PathSegment[],
): void {
	if (!isWellFormed.call(value)) {
		throw new Error(`Cannot ${verb} ill-formed Unicode string at ${formatPath(path)}`);
	}
}

function dateToWire(value: Date, path: PathSegment[]): string {
	const time = Date.prototype.getTime.call(value);
	const year = Date.prototype.getUTCFullYear.call(value);
	if (Number.isNaN(time)) {
		throw new Error(`Cannot serialize invalid Date at ${formatPath(path)}`);
	}
	if (year < 1 || year > 9999) {
		throw new Error(
			`Cannot serialize Date outside supported year range 0001-9999 at ${formatPath(path)}`,
		);
	}
	return Date.prototype.toISOString.call(value);
}

function dateFromWire(value: string, path: PathSegment[]): Date {
	validateString(value, "deserialize", path);
	const match = DATETIME_RE.exec(value);
	if (!match || Number(match[1]) < 1) {
		throw new Error(`Invalid datetime literal at ${formatPath(path)}: ${value}`);
	}
	const result = new Date(value);
	if (
		Number.isNaN(Date.prototype.getTime.call(result)) ||
		Date.prototype.toISOString.call(result) !== value
	) {
		throw new Error(`Invalid datetime literal at ${formatPath(path)}: ${value}`);
	}
	return result;
}

function canonicalizeSet(value: Set<unknown>, path: PathSegment[]): CanonicalSetItem[] {
	const result: CanonicalSetItem[] = [];
	const collisions = new Set<string>();
	const iterator = Set.prototype.values.call(value) as IterableIterator<unknown>;
	let index = 0;
	for (const entry of iterator) {
		const item = describeSetInput(entry, path, index);
		if (collisions.has(item.collisionKey)) {
			throw new Error(
				`Cannot serialize cross-runtime-colliding Set value at ${formatSetPath(path, "set", index)}`,
			);
		}
		collisions.add(item.collisionKey);
		result.push(item);
		index += 1;
	}
	result.sort(compareSetItems);
	return result;
}

function describeSetInput(
	value: unknown,
	path: PathSegment[],
	index: number,
): CanonicalSetItem {
	if (value === undefined || value === null || (typeof value === "number" && Number.isNaN(value))) {
		return describePortableSetValue(null);
	}
	if (typeof value === "number") {
		validateFiniteNumber(value, "serialize", path);
		return describePortableSetValue(Object.is(value, -0) ? 0 : value);
	}
	if (typeof value === "string") {
		if (!isWellFormed.call(value)) {
			throw new Error(
				`Cannot serialize ill-formed Unicode string at ${formatSetPath(path, "set", index)}`,
			);
		}
		return describePortableSetValue(value);
	}
	if (typeof value === "boolean") {
		return describePortableSetValue(value);
	}
	if (value instanceof Date) {
		dateToWire(value, path);
		return describePortableSetValue(value);
	}
	throw new TypeError(
		`Cannot serialize non-portable Set value of type ${valueTypeName(value)} at ${formatSetPath(path, "set", index)}`,
	);
}

function describeDecodedSetValue(
	value: unknown,
	path: PathSegment[],
): CanonicalSetItem {
	if (
		value === null ||
		typeof value === "boolean" ||
		typeof value === "number" ||
		typeof value === "string" ||
		value instanceof Date
	) {
		return describePortableSetValue(value);
	}
	throw new Error(`Cannot deserialize non-portable Set value at ${formatPath(path)}`);
}

function describePortableSetValue(value: PortableSetValue): CanonicalSetItem {
	if (value === null) {
		return {
			value,
			rank: 0,
			number: 0,
			text: "",
			collisionKey: "null",
		};
	}
	if (typeof value === "boolean") {
		return {
			value,
			rank: 1,
			number: Number(value),
			text: "",
			collisionKey: value ? "bool-number:1" : "bool-number:0",
		};
	}
	if (typeof value === "number") {
		return {
			value,
			rank: 2,
			number: value,
			text: "",
			collisionKey:
				value === 0 || value === 1 ? `bool-number:${value}` : `number:${String(value)}`,
		};
	}
	if (typeof value === "string") {
		return {
			value,
			rank: 3,
			number: 0,
			text: value,
			collisionKey: `string:${value}`,
		};
	}
	const text = Date.prototype.toISOString.call(value);
	return {
		value,
		rank: 4,
		number: 0,
		text,
		collisionKey: `datetime:${text}`,
	};
}

function compareSetItems(left: CanonicalSetItem, right: CanonicalSetItem): number {
	if (left.rank !== right.rank) {
		return left.rank - right.rank;
	}
	if (left.rank === 1 || left.rank === 2) {
		return left.number < right.number ? -1 : left.number > right.number ? 1 : 0;
	}
	return compareCodePoints(left.text, right.text);
}

function compareCodePoints(left: string, right: string): number {
	let leftIndex = 0;
	let rightIndex = 0;
	while (leftIndex < left.length && rightIndex < right.length) {
		const leftCodePoint = left.codePointAt(leftIndex) as number;
		const rightCodePoint = right.codePointAt(rightIndex) as number;
		if (leftCodePoint !== rightCodePoint) {
			return leftCodePoint - rightCodePoint;
		}
		leftIndex += leftCodePoint > 0xffff ? 2 : 1;
		rightIndex += rightCodePoint > 0xffff ? 2 : 1;
	}
	return left.length - right.length;
}

function decodeIdentityId(value: number, path: PathSegment[]): number {
	if (!Number.isSafeInteger(value) || value < 0) {
		throw new Error(`Invalid identity id at ${formatPath(path)}: ${String(value)}`);
	}
	return Object.is(value, -0) ? 0 : value;
}

function assertMarkerLength(marker: unknown[], expected: number, path: PathSegment[]): void {
	if (marker.length !== expected) {
		throw new Error(`Malformed marker at ${formatPath(path)}`);
	}
}

function defineRecordValue(result: Record<string, any>, key: string, value: any): void {
	if (key === "__proto__") {
		Object.defineProperty(result, key, {
			value,
			enumerable: true,
			configurable: true,
			writable: true,
		});
		return;
	}
	result[key] = value;
}

function formatPath(path: PathSegment[]): string {
	let result = "$";
	for (let index = 0; index < path.length; index += 1) {
		const segment = path[index];
		if (typeof segment === "number") {
			result += `[${segment}]`;
		} else if (segment.startsWith("<")) {
			result += segment;
		} else if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(segment)) {
			result += `.${segment}`;
		} else {
			result += `[${JSON.stringify(segment)}]`;
		}
	}
	return result;
}

function formatSetPath(
	path: PathSegment[],
	kind: "set" | "map",
	index: number,
): string {
	return `${formatPath(path)}<${kind}:${index}>`;
}

function valueTypeName(value: unknown): string {
	if (value === null) return "null";
	if (typeof value !== "object") return typeof value;
	return value.constructor?.name ?? "object";
}

function prototypeName(prototype: object | null): string {
	if (prototype === null) return "null";
	return prototype.constructor?.name ?? "unknown";
}
