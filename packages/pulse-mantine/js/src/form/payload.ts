export function stripFilesForSync(value: any): any {
	if (value == null) return value;
	if (typeof File !== "undefined" && value instanceof File) return undefined;
	if (typeof FileList !== "undefined" && value instanceof FileList) return [];
	if (Array.isArray(value)) {
		const result: any[] = [];
		for (const item of value) {
			const stripped = stripFilesForSync(item);
			if (stripped !== undefined) result.push(stripped);
		}
		return result;
	}
	if (value instanceof Date || value instanceof Map || value instanceof Set) {
		return value;
	}
	if (typeof value === "object") {
		const proto = Object.getPrototypeOf(value);
		if (proto !== Object.prototype && proto !== null) return value;
		const result: Record<string, any> = {};
		for (const key of Object.keys(value)) {
			const stripped = stripFilesForSync(value[key]);
			if (stripped !== undefined) result[key] = stripped;
		}
		return result;
	}
	return value;
}
