import type { ReactNode } from "react";
import { VDOMRenderer } from "../renderer";
import type { ComponentRegistry, VDOMNode } from "../vdom";

export type Primitive = number | string | boolean | null | undefined;
export type JSON<T> = T | Array<JSON<T>> | { [K: string]: JSON<T> };
export type PlainJSON = JSON<Primitive>;
export type Serializable = any;

export type Serialized = [[number[], number[], number[], number[], number[]], PlainJSON];

export function serialize(data: Serializable): Serialized {
	const seen = new Map<any, number>();
	const refs: number[] = [];
	const dates: number[] = [];
	const sets: number[] = [];
	const maps: number[] = [];
	const pulseNodes: number[] = [];

	// Single global counter - increments once per payload slot visit
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

		throw new Error(`Unsupported value in serialization: ${value}`);
	}

	const payload = process(data);
	return [[refs, dates, sets, maps, pulseNodes], payload];
}

export interface DeserializationOptions {
	coerceNullsToUndefined?: boolean;
	registry?: ComponentRegistry;
	renderer?: Pick<VDOMRenderer, "renderNode">;
}

export function deserialize<Data extends Serializable = Serializable>(
	payload: Serialized,
	options?: DeserializationOptions,
): Data {
	const [metadata, data] = payload;
	const [refsA, datesA, setsA, mapsA, pulseNodesA] = metadata;

	const refs = new Set(refsA);
	const dates = new Set(datesA);
	const sets = new Set(setsA);
	const maps = new Set(mapsA);
	const pulseNodes = new Set(pulseNodesA);
	const pulseRenderer = options?.renderer
		? options.renderer
		: options?.registry
			? VDOMRenderer.snapshot(options.registry)
			: undefined;
	if (pulseNodes.size > 0 && !pulseRenderer) {
		throw new Error("[Pulse] Payload contains VDOM nodes but no renderer or registry was provided");
	}

	const objects: Array<any> = [];
	let globalIndex = 0;

	function reconstruct(value: PlainJSON): any {
		const idx = globalIndex++;
		const shouldRenderPulseNode = pulseNodes.has(idx);
		if (refs.has(idx)) {
			if (typeof value !== "number") {
				throw new Error("Reference payload must be a numeric index");
			}
			objects[idx] = null;
			if (!(value in objects)) {
				throw new Error(`Dangling reference to index ${value}`);
			}
			return objects[value];
		}

		function finish(result: any) {
			if (!shouldRenderPulseNode) {
				return result;
			}
			const node = pulseRenderer!.renderNode(result as VDOMNode) as ReactNode;
			objects[idx] = node;
			return node;
		}

		if (dates.has(idx)) {
			if (typeof value !== "string") {
				throw new Error("Date payload must be an ISO string");
			}
			const literal = parseDateLiteral(value);
			if (literal) {
				const [y, m, d] = literal;
				const dt = new Date(Date.UTC(y, m - 1, d));
				objects[idx] = dt;
				return dt;
			}
			if (isDateLiteral(value)) {
				throw new Error(`Invalid date literal: ${value}`);
			}
			const dt = new Date(value);
			objects[idx] = dt;
			return dt;
		}

		if (isPrimitive(value)) {
			if (shouldRenderPulseNode) {
				throw new Error("Pulse node payload must be a VDOM node");
			}
			if (options?.coerceNullsToUndefined) {
				return value ?? undefined;
			}
			return value;
		}

		if (Array.isArray(value)) {
			if (sets.has(idx)) {
				const result = new Set();
				objects[idx] = result;
				for (let i = 0; i < value.length; i++) {
					result.add(reconstruct(value[i]));
				}
				return finish(result);
			}

			const length = value.length;
			const arr = new Array(length);
			objects[idx] = arr;
			for (let i = 0; i < length; i++) {
				arr[i] = reconstruct(value[i]);
			}
			return finish(arr);
		}

		if (typeof value === "object") {
			if (maps.has(idx)) {
				const result = new Map<string, any>();
				objects[idx] = result;
				const keys = Object.keys(value);
				for (let i = 0; i < keys.length; i++) {
					const key = keys[i];
					result.set(key, reconstruct(value[key]));
				}
				return finish(result);
			}

			const result: Record<string, any> = {};
			objects[idx] = result;
			const keys = Object.keys(value);
			for (let i = 0; i < keys.length; i++) {
				const key = keys[i];
				result[key] = reconstruct(value[key]);
			}
			return finish(result);
		}

		throw new Error(`Unsupported value in deserialization: ${value}`);
	}

	return reconstruct(data);
}

function isPrimitive(value: PlainJSON): value is Primitive {
	return (
		value == null ||
		typeof value === "number" ||
		typeof value === "string" ||
		typeof value === "boolean"
	);
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
