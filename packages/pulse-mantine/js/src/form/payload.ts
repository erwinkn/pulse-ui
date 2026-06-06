export function extractDataAndFiles(values: any) {
	const filesByPath = new Map<string, File[]>();

	function isFileLike(v: any): v is File {
		return typeof File !== "undefined" && v instanceof File;
	}

	function pushFile(path: string, file: File) {
		const existing = filesByPath.get(path);
		if (existing) existing.push(file);
		else filesByPath.set(path, [file]);
	}

	function visit(node: any, path: string): any {
		if (node == null) return node;

		// File or FileList
		if (isFileLike(node)) {
			pushFile(path, node);
			return undefined;
		}
		if (typeof FileList !== "undefined" && node instanceof FileList) {
			for (let i = 0; i < node.length; i++) pushFile(path, node.item(i)!);
			return undefined;
		}

		// Array
		if (Array.isArray(node)) {
			const result = new Array(node.length);
			for (let i = 0; i < node.length; i++) {
				const childPath = path ? `${path}.${i}` : String(i);
				result[i] = visit(node[i], childPath);
			}
			return result;
		}

		// Plain object
		if (typeof node === "object") {
			const out: Record<string, any> = {};
			const keys = Object.keys(node);
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				const childPath = path ? `${path}.${key}` : key;
				const value = visit(node[key], childPath);
				if (value !== undefined) out[key] = value;
			}
			return out;
		}

		// Primitive or other serializable values (Date, Map, Set handled by serializer)
		return node;
	}

	const dataWithoutFiles = visit(values, "");
	return { dataWithoutFiles, filesByPath } as const;
}

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
