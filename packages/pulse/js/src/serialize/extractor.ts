type Simplify<T> = { [K in keyof T]: T[K] } & {};

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
				out[key as string] =
					typeof value === "number" && !Number.isFinite(value) ? null : value;
			}
			if (computed) {
				for (const key in computed) {
					const fn = computed[key]!;
					const value = fn(src);
					if (value === undefined) continue;
					out[key] =
						typeof value === "number" && !Number.isFinite(value) ? null : value;
				}
			}
			return out;
		};
	}
	return _createExtractor;
}
