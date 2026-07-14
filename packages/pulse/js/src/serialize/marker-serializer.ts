// Standalone v5 experiment. Not exported or used by the framework.
export type Primitive = number | string | boolean | null;
export type Serializable = any;

export type WireValue =
	| Primitive
	| WireValue[]
	| { [key: string]: WireValue }
	| ["$", "a", WireValue[]]
	| ["$", "d", string]
	| ["$", "t", string]
	| ["$", "m", [string, WireValue][]]
	| ["$", "s", WireValue[]]
	| ["$", "r", number];

export type Serialized = [5, WireValue];

const VERSION = 5;
const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})(?![\s\S])/;
const DATETIME_RE =
	/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z(?![\s\S])/;

export class DateOnly {
	readonly year: number;
	readonly month: number;
	readonly day: number;

	constructor(value: string);
	constructor(year: number, month: number, day: number);
	constructor(valueOrYear: string | number, month?: number, day?: number) {
		if (typeof valueOrYear === "string") {
			const parts = parseDateOnlyParts(valueOrYear, "$");
			this.year = parts.year;
			this.month = parts.month;
			this.day = parts.day;
			return;
		}
		if (month === undefined || day === undefined) {
			throw new Error(
				"DateOnly requires either an ISO date string or year, month, day",
			);
		}
		assertDateParts(valueOrYear, month, day, "$");
		this.year = valueOrYear;
		this.month = month;
		this.day = day;
	}

	static parse(value: string, path = "$"): DateOnly {
		const parts = parseDateOnlyParts(value, path);
		return new DateOnly(parts.year, parts.month, parts.day);
	}

	toString(): string {
		return formatDateOnlyParts(this.year, this.month, this.day);
	}

	toJSON(): string {
		return this.toString();
	}
}

export function serialize(data: Serializable): Serialized {
	const seen = new Map<object, number>();

	function encode(value: Serializable, path: string): WireValue {
		if (
			value === null ||
			typeof value === "boolean"
		) {
			return value;
		}
		if (typeof value === "string") {
			validatePortableString(value, path, "serialize");
			return value;
		}

		if (typeof value === "number") {
			validateNumber(value, path, "serialize");
			return value;
		}

		if (value === undefined) {
			throw new Error(`Cannot serialize undefined at ${path}`);
		}
		if (typeof value === "function") {
			throw new Error(`Cannot serialize function at ${path}`);
		}
		if (typeof value === "symbol") {
			throw new Error(`Cannot serialize symbol at ${path}`);
		}
		if (typeof value === "bigint") {
			throw new Error(`Cannot serialize bigint at ${path}`);
		}
		if (typeof value !== "object") {
			throw new Error(
				`Cannot serialize value of type '${typeof value}' at ${path}`,
			);
		}

		const existingId = seen.get(value);
		if (existingId !== undefined) {
			return ["$", "r", existingId];
		}
		seen.set(value, seen.size);

		if (value instanceof DateOnly) {
			assertDateParts(value.year, value.month, value.day, path);
			return ["$", "d", formatDateOnlyParts(value.year, value.month, value.day)];
		}
		if (value instanceof Date) {
			validateDate(value, path);
			return ["$", "t", dateToWire(value)];
		}
		if (Array.isArray(value)) {
			const sourceItems = readDenseArrayItems(value, path, "serialize");
			const items = new Array<WireValue>(sourceItems.length);
			for (let index = 0; index < sourceItems.length; index += 1) {
				items[index] = encode(sourceItems[index], childPath(path, index));
			}
			if (items.length > 0 && items[0] === "$") {
				return ["$", "a", items];
			}
			return items;
		}
		if (value instanceof Map) {
			const entries: [string, WireValue][] = [];
			const sourceEntries = Map.prototype.entries.call(value) as IterableIterator<
				[unknown, unknown]
			>;
			for (const [key, entry] of sourceEntries) {
				if (typeof key !== "string") {
					throw new Error(
						`Cannot serialize Map with non-string key at ${path}`,
					);
				}
				validatePortableString(key, path, "serialize");
				entries.push([key, encode(entry, childPath(path, key))]);
			}
			return ["$", "m", entries];
		}
		if (value instanceof Set) {
			const items = getCanonicalSetItems(value, path);
			items.sort(comparePortableSetValues);
			return [
				"$",
				"s",
				items.map((entry, index) => encode(entry, setEntryPath(path, index))),
			];
		}
		const result: Record<string, WireValue> = Object.create(null);
		for (const key of getRecordKeys(value, path)) {
			result[key] = encode(
				(value as Record<string, Serializable>)[key],
				childPath(path, key),
			);
		}
		return result;
	}

	return [VERSION, encode(data, "$")];
}

export function deserialize<Data extends Serializable = Serializable>(
	payload: Serialized,
): Data {
	if (!Array.isArray(payload)) {
		throw new Error("Malformed serialized envelope");
	}
	const envelope = readDenseArrayItems(payload, "$", "deserialize");
	if (envelope.length !== 2) {
		throw new Error("Malformed serialized envelope");
	}
	if (envelope[0] !== VERSION) {
		throw new Error(`Unknown serialization version: ${String(envelope[0])}`);
	}

	const defined: any[] = [];

	function register<T>(value: T): T {
		defined.push(value);
		return value;
	}

	function decode(value: WireValue, path: string): any {
		if (value === null) {
			return null;
		}
		if (typeof value === "boolean") {
			return value;
		}
		if (typeof value === "string") {
			validatePortableString(value, path, "deserialize");
			return value;
		}
		if (typeof value === "number") {
			validateNumber(value, path, "deserialize");
			return Object.is(value, -0) ? 0 : value;
		}
		if (Array.isArray(value)) {
			const items = readDenseArrayItems(
				value,
				path,
				"deserialize",
			) as WireValue[];
			if (items.length > 0 && items[0] === "$") {
				return decodeMarker(items, path);
			}
			const result = register(new Array(items.length));
			for (let index = 0; index < items.length; index += 1) {
				result[index] = decode(items[index], childPath(path, index));
			}
			return result;
		}
		assertPlainWireObject(value, path);
		const result = register({} as Record<string, any>);
		for (const key of Object.keys(value)) {
			validatePortableString(key, path, "deserialize");
			const entry = decode(value[key], childPath(path, key));
			if (key === "__proto__") {
				Object.defineProperty(result, key, {
					value: entry,
					enumerable: true,
					configurable: true,
					writable: true,
				});
			} else {
				result[key] = entry;
			}
		}
		return result;
	}

	function decodeMarker(value: WireValue[], path: string): any {
		if (value.length < 2 || value[0] !== "$" || typeof value[1] !== "string") {
			throw new Error(`Malformed marker at ${path}`);
		}

		const tag = value[1];
		validatePortableString(tag, path, "deserialize");
		switch (tag) {
			case "a": {
				assertMarkerLength(value, 3, path);
				if (!Array.isArray(value[2])) {
					throw new Error(`Escaped array payload must be an array at ${path}`);
				}
				const items = readDenseArrayItems(value[2], path, "deserialize");
				if (items.length === 0 || items[0] !== "$") {
					throw new Error(`Escaped array payload must begin with '$' at ${path}`);
				}
				const result = register(new Array(items.length));
				for (let index = 0; index < items.length; index += 1) {
					result[index] = decode(
						items[index] as WireValue,
						childPath(path, index),
					);
				}
				return result;
			}
			case "d": {
				assertMarkerLength(value, 3, path);
				if (typeof value[2] !== "string") {
					throw new Error(`DateOnly payload must be a string at ${path}`);
				}
				return register(DateOnly.parse(value[2], path));
			}
			case "t": {
				assertMarkerLength(value, 3, path);
				if (typeof value[2] !== "string") {
					throw new Error(`Datetime payload must be a string at ${path}`);
				}
				return register(parseDateTime(value[2], path));
			}
			case "m": {
				assertMarkerLength(value, 3, path);
				return decodeMap(value[2], path);
			}
			case "s": {
				assertMarkerLength(value, 3, path);
				return decodeSet(value[2], path);
			}
			case "r": {
				assertMarkerLength(value, 3, path);
				const id = parseIdentityId(value[2], path);
				if (id >= defined.length) {
					throw new Error(`Dangling reference to id ${id} at ${path}`);
				}
				return defined[id];
			}
			default:
				throw new Error(`Unknown marker tag '${tag}' at ${path}`);
		}
	}

	function decodeMap(rawEntries: unknown, path: string): Map<string, any> {
		const result = register(new Map<string, any>());
		fillMap(result, rawEntries, path);
		return result;
	}

	function fillMap(
		target: Map<string, any>,
		rawEntries: unknown,
		path: string,
	): void {
		if (!Array.isArray(rawEntries)) {
			throw new Error(`Map payload must be an array at ${path}`);
		}
		const entries = readDenseArrayItems(rawEntries, path, "deserialize");
		const seenKeys = new Set<string>();
		for (let index = 0; index < entries.length; index += 1) {
			const rawEntry = entries[index];
			if (!Array.isArray(rawEntry)) {
				throw new Error(
					`Map entry must be [string, value] at ${childPath(path, index)}`,
				);
			}
			const entry = readDenseArrayItems(
				rawEntry,
				childPath(path, index),
				"deserialize",
			);
			if (entry.length !== 2 || typeof entry[0] !== "string") {
				throw new Error(
					`Map entry must be [string, value] at ${childPath(path, index)}`,
				);
			}
			const key = entry[0];
			validatePortableString(key, childPath(path, index), "deserialize");
			if (seenKeys.has(key)) {
				throw new Error(
					`Duplicate Map key '${key}' at ${childPath(path, index)}`,
				);
			}
			seenKeys.add(key);
			target.set(
				key,
				decode(entry[1] as WireValue, childPath(path, key)),
			);
		}
	}

	function decodeSet(rawItems: unknown, path: string): Set<any> {
		const result = register(new Set<any>());
		fillSet(result, rawItems, path);
		return result;
	}

	function fillSet(target: Set<any>, rawItems: unknown, path: string): void {
		if (!Array.isArray(rawItems)) {
			throw new Error(`Set payload must be an array at ${path}`);
		}
		const items = readDenseArrayItems(rawItems, path, "deserialize");
		const seenPortable = new Map<string, number>();
		let previous: Primitive | Date | DateOnly | undefined;
		for (let index = 0; index < items.length; index += 1) {
			const entry = toDecodedPortableSetValue(
				decode(items[index] as WireValue, childPath(path, index)),
				setEntryPath(path, index),
			);
			if (previous !== undefined && comparePortableSetValues(previous, entry) > 0) {
				throw new Error(
					`Set entries are not canonically ordered at ${setEntryPath(path, index)}`,
				);
			}
			previous = entry;
			const key = getPythonSetCollisionKey(entry);
			if (seenPortable.has(key)) {
				throw new Error(
					`Set contains duplicate portable value at ${setEntryPath(path, index)}`,
				);
			}
			seenPortable.set(key, index);
			target.add(entry);
		}
	}

	return decode(envelope[1] as WireValue, "$");
}

function readDenseArrayItems(
	value: unknown[],
	path: string,
	verb: "serialize" | "deserialize",
): unknown[] {
	const descriptors = Object.getOwnPropertyDescriptors(value);
	const items = new Array<unknown>(value.length);
	for (let index = 0; index < value.length; index += 1) {
		const descriptor = descriptors[String(index)];
		if (descriptor === undefined) {
			if (verb === "serialize") {
				throw new Error(
					`Cannot serialize sparse array at ${childPath(path, index)}`,
				);
			}
			throw new Error(`Malformed wire array at ${childPath(path, index)}`);
		}
		if (!descriptor.enumerable || !("value" in descriptor)) {
			throw new Error(
				verb === "serialize"
					? `Cannot serialize malformed array at ${childPath(path, index)}`
					: `Malformed wire array at ${childPath(path, index)}`,
			);
		}
		items[index] = descriptor.value;
	}
	if (Reflect.ownKeys(descriptors).length !== value.length + 1) {
		throw new Error(
			verb === "serialize"
				? `Cannot serialize malformed array at ${path}`
				: `Malformed wire array at ${path}`,
		);
	}
	return items;
}

function getCanonicalSetItems(
	value: Set<unknown>,
	path: string,
): Array<Primitive | Date | DateOnly> {
	const items: Array<Primitive | Date | DateOnly> = [];
	const collisions = new Map<string, number>();
	let index = 0;
	const sourceItems = Set.prototype.values.call(value) as IterableIterator<unknown>;
	for (const entry of sourceItems) {
		const entryPath = setEntryPath(path, index);
		const portable = toPortableSetValue(entry, entryPath);
		const collisionKey = getPythonSetCollisionKey(portable);
		const previous = collisions.get(collisionKey);
		if (previous !== undefined) {
			throw new Error(
				`Cannot serialize Set with Python-equality collision at ${entryPath}; collides with ${setEntryPath(path, previous)}`,
			);
		}
		collisions.set(collisionKey, index);
		items.push(portable);
		index += 1;
	}
	return items;
}

function toPortableSetValue(
	value: unknown,
	path: string,
): Primitive | Date | DateOnly {
	if (
		value === null ||
		typeof value === "boolean" ||
		typeof value === "string"
	) {
		return value;
	}
	if (typeof value === "number") {
		validateNumber(value, path, "serialize");
		return value;
	}
	if (value instanceof DateOnly) {
		return value;
	}
	if (value instanceof Date) {
		validateDate(value, path);
		return value;
	}
	if (value === undefined) {
		throw new Error(`Cannot serialize undefined at ${path}`);
	}
	if (typeof value === "function") {
		throw new Error(`Cannot serialize function at ${path}`);
	}
	if (typeof value === "symbol") {
		throw new Error(`Cannot serialize symbol at ${path}`);
	}
	if (typeof value === "bigint") {
		throw new Error(`Cannot serialize bigint at ${path}`);
	}
	throw new Error(`Cannot serialize non-portable Set value at ${path}`);
}

function toDecodedPortableSetValue(
	value: unknown,
	path: string,
): Primitive | Date | DateOnly {
	if (
		value === null ||
		typeof value === "boolean" ||
		typeof value === "string"
	) {
		return value;
	}
	if (typeof value === "number") {
		validateNumber(value, path, "deserialize");
		return value;
	}
	if (value instanceof DateOnly) {
		return value;
	}
	if (value instanceof Date) {
		validateDate(value, path);
		return value;
	}
	throw new Error(`Cannot deserialize non-portable Set value at ${path}`);
}

function getPythonSetCollisionKey(value: Primitive | Date | DateOnly): string {
	if (value === true || value === 1) {
		return "py:1";
	}
	if (value === false || value === 0) {
		return "py:0";
	}
	if (value instanceof DateOnly) {
		return `py:dateonly:${formatDateOnlyParts(value.year, value.month, value.day)}`;
	}
	if (value instanceof Date) {
		return `py:datetime:${dateToWire(value)}`;
	}
	if (value === null) {
		return "py:null";
	}
	if (typeof value === "string") {
		return `py:string:${value}`;
	}
	if (typeof value === "number") {
		return `py:number:${Object.is(value, -0) ? "-0" : String(value)}`;
	}
	return value ? "py:true" : "py:false";
}

function comparePortableSetValues(
	left: Primitive | Date | DateOnly,
	right: Primitive | Date | DateOnly,
): number {
	const leftRank = portableSetRank(left);
	const rightRank = portableSetRank(right);
	if (leftRank !== rightRank) {
		return leftRank - rightRank;
	}
	if (typeof left === "boolean" && typeof right === "boolean") {
		return Number(left) - Number(right);
	}
	if (typeof left === "number" && typeof right === "number") {
		return left < right ? -1 : left > right ? 1 : 0;
	}
	return compareUnicodeCodePoints(
		portableSetText(left),
		portableSetText(right),
	);
}

function portableSetRank(value: Primitive | Date | DateOnly): number {
	if (value === null) return 0;
	if (typeof value === "boolean") return 1;
	if (typeof value === "number") return 2;
	if (typeof value === "string") return 3;
	if (value instanceof DateOnly) return 4;
	return 5;
}

function portableSetText(value: Primitive | Date | DateOnly): string {
	if (typeof value === "string") return value;
	if (value instanceof DateOnly) {
		return formatDateOnlyParts(value.year, value.month, value.day);
	}
	if (value instanceof Date) return dateToWire(value);
	return "";
}

function compareUnicodeCodePoints(left: string, right: string): number {
	const leftCodePoints = Array.from(
		left,
		(value) => value.codePointAt(0) as number,
	);
	const rightCodePoints = Array.from(
		right,
		(value) => value.codePointAt(0) as number,
	);
	const length = Math.min(leftCodePoints.length, rightCodePoints.length);
	for (let index = 0; index < length; index += 1) {
		if (leftCodePoints[index] !== rightCodePoints[index]) {
			return leftCodePoints[index] - rightCodePoints[index];
		}
	}
	return leftCodePoints.length - rightCodePoints.length;
}

function validateNumber(
	value: number,
	path: string,
	verb: "serialize" | "deserialize",
): void {
	if (!Number.isFinite(value)) {
		throw new Error(`Cannot ${verb} non-finite number at ${path}`);
	}
	if (verb === "serialize" && Object.is(value, -0)) {
		throw new Error(`Cannot ${verb} negative zero at ${path}`);
	}
	if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
		throw new Error(`Cannot ${verb} unsafe integer at ${path}`);
	}
}

function validatePortableString(
	value: string,
	path: string,
	verb: "serialize" | "deserialize",
): void {
	for (let index = 0; index < value.length; index += 1) {
		const codeUnit = value.charCodeAt(index);
		if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
			const next = value.charCodeAt(index + 1);
			if (next >= 0xdc00 && next <= 0xdfff) {
				index += 1;
				continue;
			}
			throw new Error(`Cannot ${verb} surrogate code point at ${path}`);
		}
		if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
			throw new Error(`Cannot ${verb} surrogate code point at ${path}`);
		}
	}
}

function validateDate(value: Date, path: string): void {
	if (Number.isNaN(Date.prototype.getTime.call(value))) {
		throw new Error(`Cannot serialize invalid Date at ${path}`);
	}
	const year = Date.prototype.getUTCFullYear.call(value);
	if (year < 1 || year > 9999) {
		throw new Error(
			`Cannot serialize Date outside supported year range 0001-9999 at ${path}`,
		);
	}
}

function dateToWire(value: Date): string {
	return Date.prototype.toISOString.call(value);
}

function parseDateTime(value: string, path: string): Date {
	const match = DATETIME_RE.exec(value);
	if (!match) {
		throw new Error(`Invalid datetime literal at ${path}: ${value}`);
	}
	const year = Number(match[1]);
	if (year < 1 || year > 9999) {
		throw new Error(`Invalid datetime literal at ${path}: ${value}`);
	}
	const parsed = new Date(value);
	if (
		Number.isNaN(Date.prototype.getTime.call(parsed)) ||
		dateToWire(parsed) !== value
	) {
		throw new Error(`Invalid datetime literal at ${path}: ${value}`);
	}
	return parsed;
}

function parseDateOnlyParts(
	value: string,
	path: string,
): { year: number; month: number; day: number } {
	const match = DATE_ONLY_RE.exec(value);
	if (!match) {
		throw new Error(`Invalid date literal at ${path}: ${value}`);
	}
	const year = Number(match[1]);
	const month = Number(match[2]);
	const day = Number(match[3]);
	assertDateParts(year, month, day, path, value);
	return { year, month, day };
}

function assertDateParts(
	year: number,
	month: number,
	day: number,
	path: string,
	literal?: string,
): void {
	if (
		!Number.isInteger(year) ||
		!Number.isInteger(month) ||
		!Number.isInteger(day) ||
		year < 1 ||
		year > 9999
	) {
		throw new Error(
			`Invalid date literal at ${path}: ${literal ?? formatDateOnlyParts(year, month, day)}`,
		);
	}
	const date = new Date(0);
	date.setUTCHours(0, 0, 0, 0);
	date.setUTCFullYear(year, month - 1, day);
	if (
		date.getUTCFullYear() !== year ||
		date.getUTCMonth() !== month - 1 ||
		date.getUTCDate() !== day
	) {
		throw new Error(
			`Invalid date literal at ${path}: ${literal ?? formatDateOnlyParts(year, month, day)}`,
		);
	}
}

function formatDateOnlyParts(year: number, month: number, day: number): string {
	return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function parseIdentityId(value: unknown, path: string): number {
	if (
		typeof value !== "number" ||
		!Number.isInteger(value) ||
		value < 0 ||
		!Number.isSafeInteger(value)
	) {
		throw new Error(
			`Identity id must be a non-negative safe integer at ${path}`,
		);
	}
	return Object.is(value, -0) ? 0 : value;
}

function assertMarkerLength(
	value: WireValue[],
	expected: number,
	path: string,
): void {
	if (value.length !== expected) {
		throw new Error(`Malformed marker '${String(value[1])}' at ${path}`);
	}
}

function assertPlainWireObject(
	value: unknown,
	path: string,
): asserts value is { [key: string]: WireValue } {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		throw new Error(`Malformed wire object at ${path}`);
	}
	const prototype = Object.getPrototypeOf(value);
	if (prototype !== Object.prototype && prototype !== null) {
		throw new Error(`Malformed wire object at ${path}`);
	}
	if (Object.getOwnPropertySymbols(value).length > 0) {
		throw new Error(`Malformed wire object at ${path}`);
	}
	for (const descriptor of Object.values(
		Object.getOwnPropertyDescriptors(value),
	)) {
		if (!descriptor.enumerable || !("value" in descriptor)) {
			throw new Error(`Malformed wire object at ${path}`);
		}
	}
}

function childPath(path: string, segment: number | string): string {
	if (typeof segment === "number") {
		return `${path}[${segment}]`;
	}
	if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(segment)) {
		return `${path}.${segment}`;
	}
	return `${path}[${JSON.stringify(segment)}]`;
}

function getRecordKeys(value: object, path: string): string[] {
	const symbolKeys = Object.getOwnPropertySymbols(value);
	if (symbolKeys.length > 0) {
		throw new Error(
			`Cannot serialize symbol-keyed property at ${path}: ${String(symbolKeys[0])}`,
		);
	}
	const keys = Object.keys(value);
	for (const key of keys) {
		validatePortableString(key, path, "serialize");
	}
	return keys;
}

function setEntryPath(path: string, index: number): string {
	return `${path}<set:${index}>`;
}
