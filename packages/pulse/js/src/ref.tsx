import type { ChannelBridge } from "./channel";
import type { PulseRefSpec } from "./vdom";

type RefPayload = {
	refId?: string;
	op?: string;
	payload?: any;
};

type RefOpResult = any;

type RefEntry = {
	node: any;
	callback: (node: any) => void;
};

type ChannelBridgeProvider = (channelId: string) => ChannelBridge;

const ATTR_ALIASES: Record<string, string> = {
	className: "class",
	htmlFor: "for",
	tabIndex: "tabindex",
};

const ATTR_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_:\-\.]*$/;

const GETTABLE_PROPS = new Set([
	"value",
	"checked",
	"disabled",
	"readOnly",
	"selectedIndex",
	"selectionStart",
	"selectionEnd",
	"selectionDirection",
	"scrollTop",
	"scrollLeft",
	"scrollHeight",
	"scrollWidth",
	"clientWidth",
	"clientHeight",
	"offsetWidth",
	"offsetHeight",
	"innerText",
	"textContent",
	"className",
	"id",
	"name",
	"type",
	"tabIndex",
]);

const SETTABLE_PROPS = new Set([
	"value",
	"checked",
	"disabled",
	"readOnly",
	"selectedIndex",
	"selectionStart",
	"selectionEnd",
	"selectionDirection",
	"scrollTop",
	"scrollLeft",
	"className",
	"id",
	"name",
	"type",
	"tabIndex",
]);

function isRefPayload(value: unknown): value is RefPayload {
	return typeof value === "object" && value !== null;
}

function normalizeAttrName(name: string): string {
	return ATTR_ALIASES[name] ?? name;
}

function ensureAttrName(value: unknown): string {
	if (typeof value !== "string") {
		throw new Error("ref attribute name must be a string");
	}
	const trimmed = value.trim();
	if (!trimmed) {
		throw new Error("ref attribute name must be non-empty");
	}
	const normalized = normalizeAttrName(trimmed);
	if (!ATTR_NAME_PATTERN.test(normalized)) {
		throw new Error(`invalid attribute name: ${normalized}`);
	}
	if (normalized.toLowerCase().startsWith("on")) {
		throw new Error("ref attribute name cannot start with 'on'");
	}
	return normalized;
}

function ensurePropName(value: unknown, settable: boolean): string {
	if (typeof value !== "string") {
		throw new Error("ref property name must be a string");
	}
	const trimmed = value.trim();
	if (!trimmed) {
		throw new Error("ref property name must be non-empty");
	}
	if (!GETTABLE_PROPS.has(trimmed)) {
		throw new Error(`unsupported ref property: ${trimmed}`);
	}
	if (settable && !SETTABLE_PROPS.has(trimmed)) {
		throw new Error(`ref property is read-only: ${trimmed}`);
	}
	return trimmed;
}

function ensureElement(node: any): Element {
	if (!node || typeof node.getAttribute !== "function") {
		throw new Error("ref is not bound to a DOM element");
	}
	return node as Element;
}

function ensureHTMLElement(node: any): HTMLElement {
	if (!node || typeof (node as HTMLElement).style === "undefined") {
		throw new Error("ref is not bound to an HTML element");
	}
	return node as HTMLElement;
}

function parseScrollOptions(payload: any): ScrollToOptions | undefined {
	if (!payload || typeof payload !== "object") return undefined;
	const options: ScrollToOptions = {};
	if (typeof payload.top === "number") options.top = payload.top;
	if (typeof payload.left === "number") options.left = payload.left;
	if (typeof payload.behavior === "string") {
		options.behavior = payload.behavior as ScrollBehavior;
	}
	return Object.keys(options).length > 0 ? options : undefined;
}

function parseScrollIntoViewOptions(payload: any): ScrollIntoViewOptions | undefined {
	if (!payload || typeof payload !== "object") return undefined;
	const options: ScrollIntoViewOptions = {};
	if (typeof payload.behavior === "string") {
		options.behavior = payload.behavior as ScrollBehavior;
	}
	if (typeof payload.block === "string") {
		options.block = payload.block as ScrollLogicalPosition;
	}
	if (typeof payload.inline === "string") {
		options.inline = payload.inline as ScrollLogicalPosition;
	}
	return Object.keys(options).length > 0 ? options : undefined;
}

function normalizeStyleValue(value: unknown): string | null {
	if (value == null) return null;
	if (typeof value === "string") return value;
	if (typeof value === "number") return String(value);
	throw new Error("style values must be strings or numbers");
}

function parseRefPayload(payload: unknown): {
	refId: string | null;
	op: string | null;
	payload: any;
} {
	if (!isRefPayload(payload)) {
		return { refId: null, op: null, payload: null };
	}
	const refId = payload.refId;
	const op = payload.op;
	return {
		refId: refId == null ? null : String(refId),
		op: typeof op === "string" ? op : null,
		payload: payload.payload,
	};
}

export function isPulseRefSpec(v: unknown): v is PulseRefSpec {
	return typeof v === "object" && v !== null && "__pulse_ref__" in (v as any);
}

export class RefRegistry {
	#getBridge: ChannelBridgeProvider;
	#bridge: ChannelBridge | null = null;
	#channelId: string | null = null;
	#entries: Map<string, RefEntry> = new Map();
	#cleanup: Array<() => void> = [];

	constructor(getBridge: ChannelBridgeProvider) {
		this.#getBridge = getBridge;
	}

	getCallback(channelId: string, refId: string): (node: any) => void {
		this.#ensureChannel(channelId);
		let entry = this.#entries.get(refId);
		if (!entry) {
			const callback = (node: any) => {
				this.#setNode(refId, node ?? null);
			};
			entry = { node: null, callback };
			this.#entries.set(refId, entry);
		}
		return entry.callback;
	}

	dispose(): void {
		this.#teardown();
	}

	#ensureChannel(channelId: string): void {
		if (this.#bridge) {
			if (this.#channelId !== channelId) {
				throw new Error("[Pulse] Ref channel changed unexpectedly");
			}
			return;
		}
		const bridge = this.#getBridge(channelId);
		this.#bridge = bridge;
		this.#channelId = channelId;
		this.#cleanup.push(
			bridge.on("ref:call", (payload) => {
				this.#handleCall(payload);
			}),
			bridge.on("ref:request", (payload) => {
				return this.#handleRequest(payload);
			}),
		);
	}

	#teardown(): void {
		for (const fn of this.#cleanup) fn();
		this.#cleanup = [];
		this.#entries.clear();
		this.#bridge = null;
		this.#channelId = null;
	}

	#setNode(refId: string, node: any): void {
		const entry = this.#entries.get(refId);
		if (!entry) return;
		if (entry.node === node) return;
		entry.node = node;
		const bridge = this.#bridge;
		if (!bridge) return;
		if (node) {
			bridge.emit("ref:mounted", { refId });
		} else {
			bridge.emit("ref:unmounted", { refId });
		}
	}

	#handleCall(payload: unknown): void {
		const parsed = parseRefPayload(payload);
		if (!parsed.refId || !parsed.op) return;
		try {
			this.#perform(parsed.refId, parsed.op, parsed.payload, false);
		} catch (err) {
			console.error("[Pulse] Ref call failed:", err);
		}
	}

	#handleRequest(payload: unknown): RefOpResult {
		const parsed = parseRefPayload(payload);
		if (!parsed.op) {
			throw new Error("ref request missing op");
		}
		if (!parsed.refId) {
			throw new Error("ref request missing refId");
		}
		return this.#perform(parsed.refId, parsed.op, parsed.payload, true);
	}

	#perform(refId: string, op: string, payload: any, needsResult: boolean): RefOpResult {
		const entry = this.#entries.get(refId);
		const node = entry?.node as any;
		if (!node) {
			const msg = "ref is not mounted";
			if (needsResult) throw new Error(msg);
			console.warn(`[Pulse] ${msg}`);
			return null;
		}

		switch (op) {
			case "focus":
				if (typeof node.focus === "function") {
					if (payload && typeof payload === "object" && "preventScroll" in payload) {
						const preventScroll = Boolean((payload as any).preventScroll);
						try {
							node.focus({ preventScroll });
						} catch {
							node.focus();
						}
					} else {
						node.focus();
					}
				}
				return null;
			case "blur":
				if (typeof node.blur === "function") node.blur();
				return null;
			case "click":
				if (typeof node.click === "function") node.click();
				return null;
			case "select":
				if (typeof node.select === "function") node.select();
				else throw new Error("select() not supported on this element");
				return null;
			case "scrollIntoView": {
				if (typeof node.scrollIntoView !== "function") {
					throw new Error("scrollIntoView() not supported on this element");
				}
				const options = parseScrollIntoViewOptions(payload) ?? undefined;
				node.scrollIntoView(options);
				return null;
			}
			case "scrollTo": {
				if (typeof node.scrollTo !== "function") {
					throw new Error("scrollTo() not supported on this element");
				}
				const options = parseScrollOptions(payload);
				node.scrollTo(options ?? undefined);
				return null;
			}
			case "scrollBy": {
				if (typeof node.scrollBy !== "function") {
					throw new Error("scrollBy() not supported on this element");
				}
				const options = parseScrollOptions(payload);
				node.scrollBy(options ?? undefined);
				return null;
			}
			case "submit": {
				if (typeof node.submit !== "function") {
					throw new Error("submit() not supported on this element");
				}
				node.submit();
				return null;
			}
			case "reset": {
				if (typeof node.reset !== "function") {
					throw new Error("reset() not supported on this element");
				}
				node.reset();
				return null;
			}
			case "setSelectionRange": {
				if (typeof node.setSelectionRange !== "function") {
					throw new Error("setSelectionRange() not supported on this element");
				}
				if (!payload || typeof payload !== "object") {
					throw new Error("setSelectionRange() requires payload");
				}
				const start = (payload as any).start;
				const end = (payload as any).end;
				const direction = (payload as any).direction;
				if (typeof start !== "number" || typeof end !== "number") {
					throw new Error("setSelectionRange() requires numeric start/end");
				}
				node.setSelectionRange(start, end, direction ?? undefined);
				return null;
			}
			case "measure": {
				if (typeof node.getBoundingClientRect !== "function") {
					throw new Error("measure() not supported on this element");
				}
				const rect = node.getBoundingClientRect();
				return {
					x: rect.x,
					y: rect.y,
					width: rect.width,
					height: rect.height,
					top: rect.top,
					right: rect.right,
					bottom: rect.bottom,
					left: rect.left,
				};
			}
			case "getValue": {
				if ("value" in node) return (node as any).value;
				if ("textContent" in node) return (node as any).textContent;
				return null;
			}
			case "setValue": {
				const value = payload?.value;
				if ("value" in node) {
					(node as any).value = value;
					return (node as any).value;
				}
				if ("textContent" in node) {
					(node as any).textContent = value == null ? "" : String(value);
					return (node as any).textContent;
				}
				return null;
			}
			case "getText": {
				if ("textContent" in node) return (node as any).textContent;
				return null;
			}
			case "setText": {
				const text = payload?.text;
				if (typeof text !== "string") {
					throw new Error("setText() requires a string payload");
				}
				if ("textContent" in node) {
					(node as any).textContent = text;
					return (node as any).textContent;
				}
				return null;
			}
			case "getAttr": {
				const name = ensureAttrName(payload?.name);
				const el = ensureElement(node);
				return el.getAttribute(name);
			}
			case "setAttr": {
				const name = ensureAttrName(payload?.name);
				const el = ensureElement(node);
				const value = payload?.value;
				if (value == null) {
					el.removeAttribute(name);
				} else {
					el.setAttribute(name, String(value));
				}
				return el.getAttribute(name);
			}
			case "removeAttr": {
				const name = ensureAttrName(payload?.name);
				const el = ensureElement(node);
				el.removeAttribute(name);
				return null;
			}
			case "getProp": {
				const name = ensurePropName(payload?.name, false);
				if (!(name in node)) {
					throw new Error(`ref property not supported on element: ${name}`);
				}
				return (node as any)[name];
			}
			case "setProp": {
				const name = ensurePropName(payload?.name, true);
				if (!(name in node)) {
					throw new Error(`ref property not supported on element: ${name}`);
				}
				(node as any)[name] = payload?.value;
				return (node as any)[name];
			}
			case "setStyle": {
				const el = ensureHTMLElement(node);
				const styles = payload?.styles;
				if (!styles || typeof styles !== "object") {
					throw new Error("setStyle() requires a styles object");
				}
				for (const [rawKey, rawValue] of Object.entries(styles)) {
					if (!rawKey) {
						throw new Error("style key must be non-empty");
					}
					const value = normalizeStyleValue(rawValue);
					if (rawKey.includes("-")) {
						if (value == null) {
							el.style.removeProperty(rawKey);
						} else {
							el.style.setProperty(rawKey, value);
						}
						continue;
					}
					if (value == null) {
						(el.style as any)[rawKey] = "";
					} else {
						(el.style as any)[rawKey] = value;
					}
				}
				return null;
			}
			default:
				throw new Error(`Unsupported ref op: ${op}`);
		}
	}
}
