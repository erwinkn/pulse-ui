type Simplify<T> = { [K in keyof T]: T[K] } & {};

function normalizeExtracted(value: unknown): unknown {
	if (typeof value === "number" && !Number.isFinite(value)) {
		return null;
	}
	// Host objects (DOMTokenList, DOMStringList, ...) are not serializable;
	// list-likes become arrays, anything else becomes its string form.
	if (
		typeof value === "object" &&
		value !== null &&
		!Array.isArray(value) &&
		!(value instanceof Date) &&
		!(value instanceof Map) &&
		!(value instanceof Set) &&
		Object.getPrototypeOf(value) !== Object.prototype &&
		Object.getPrototypeOf(value) !== null
	) {
		const length = (value as { length?: unknown }).length;
		if (typeof length === "number" && Number.isFinite(length)) {
			return Array.from(value as ArrayLike<unknown>, normalizeExtracted);
		}
		return String(value);
	}
	return value;
}

export function createExtractor<T extends object>() {
	function _createExtractor<
		const K extends readonly (keyof T)[],
		C extends Partial<Record<K[number] | string, (src: T) => any>>,
	>(keys: K, computed?: C) {
		return (
			src: T,
		): Simplify<
			Pick<T, K[number]> & {
				[P in keyof C]-?: C[P] extends (...args: any) => infer R ? R : never;
			}
		> => {
			const out: any = {};
			for (const key of keys) {
				const value = (src as any)[key as string];
				if (value === undefined) continue;
				out[key as string] = normalizeExtracted(value);
			}
			if (computed) {
				for (const key in computed) {
					const fn = computed[key]!;
					const value = fn(src);
					if (value === undefined) continue;
					out[key] = normalizeExtracted(value);
				}
			}
			return out;
		};
	}
	return _createExtractor;
}
