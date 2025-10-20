export type Primitive = number | string | boolean | null | undefined;
export type JSON<T> = T | Array<JSON<T>> | { [K: string]: JSON<T> };
export type PlainJSON = JSON<Primitive>;
export type Serializable = any;

export type Serialized = [[number[], number[], number[], number[]], PlainJSON];

export function serialize(data: Serializable): Serialized {
	const seen = new Map<any, number>();
	const refs: number[] = [];
	const dates: number[] = [];
	const sets: number[] = [];
	const maps: number[] = [];

	// Single global counter - increments once per node visit
	let globalIndex = 0;

	function process(value: Serializable): PlainJSON {
		if (
			value == null ||
			typeof value === "number" ||
			typeof value === "string" ||
			typeof value === "boolean"
		) {
			return value;
		}

		const idx = globalIndex++;
		const prevRef = seen.get(value);
		if (prevRef !== undefined) {
			// Make sure to push the current index, but use the ref's index as the value!
			refs.push(idx);
			return prevRef;
		}

		seen.set(value, idx);

		if (value instanceof Date) {
			dates.push(idx);
			return value.getTime();
		}

		if (Array.isArray(value)) {
			const length = value.length;
			const result = new Array(length);
			for (let i = 0; i < length; i++) {
				result[i] = process(value[i]);
			}
			return result;
		}

		if (value instanceof Map) {
			maps.push(idx);
			const rec: Record<string, any> = {};
			for (const [key, entry] of value.entries()) {
				rec[String(key)] = process(entry);
			}
			return rec;
		}

		if (value instanceof Set) {
			sets.push(idx);
			const size = value.size;
			const result = new Array(size);
			let i = 0;
			for (const entry of value) {
				result[i] = process(entry);
				i += 1;
			}
			return result;
		}

		if (typeof value === "object") {
			const rec: Record<string, any> = {};
			const keys = Object.keys(value);
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				rec[key] = process(value[key]);
			}
			return rec;
		}

		throw new Error(`Unsupported value in serialization: ${value}`);
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

	const objects: Array<any> = [];

	function reconstruct(value: PlainJSON): any {
		const idx = objects.length;
		if (refs.has(idx)) {
			// We increment the counter on refs during serialization. We're never
			// going to use this entry, so we can just push null.
			objects.push(null);
			return objects[value as number];
		}

		if (dates.has(idx)) {
			const dt = new Date(value as number);
			objects.push(dt);
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
				objects.push(result);
				for (let i = 0; i < value.length; i++) {
					result.add(reconstruct(value[i]));
				}
				return result;
			}

			const length = value.length;
			const arr = new Array(length);
			objects.push(arr);
			for (let i = 0; i < length; i++) {
				arr[i] = reconstruct(value[i]);
			}
			return arr;
		}

		if (typeof value === "object") {
			if (maps.has(idx)) {
				const result = new Map<string, any>();
				objects.push(result);
				const keys = Object.keys(value);
				for (let i = 0; i < keys.length; i++) {
					const key = keys[i];
					result.set(key, reconstruct(value[key]));
				}
				return result;
			}

			const result: Record<string, any> = {};
			objects.push(result);
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
