import {
	type ComponentType,
	cloneElement,
	createElement,
	Fragment,
	isValidElement,
	type ReactElement,
	type ReactNode,
} from "react";
import type { PulseSocketIOClient } from "./client";
import type { PulsePrerenderView } from "./pulse";
import { extractEvent } from "./serialize/events";
import type {
	ComponentRegistry,
	JsonValue,
	VDOM,
	VDOMNode,
	VDOMPropValue,
	VDOMUpdate,
} from "./vdom";
import { isElementNode, isExprNode, MOUNT_POINT_PREFIX as REF_PREFIX } from "./vdom";

type Env = Record<string, unknown>;

type CallbackDelay = number | null;

type CallbackEntry = {
	fn: (...args: any[]) => void;
	delayMs: CallbackDelay;
	timer: ReturnType<typeof setTimeout> | null;
	lastArgs: any[] | null;
	dueAt: number | null;
};

function parseCallbackPlaceholder(value: unknown): CallbackDelay | undefined {
	if (value === "$cb") return null;
	if (typeof value !== "string" || !value.startsWith("$cb:")) return undefined;
	const raw = value.slice(4);
	if (raw.length === 0) {
		throw new Error("[Pulse] Invalid callback placeholder: '$cb:'");
	}
	const delay = Number(raw);
	if (!Number.isFinite(delay) || delay < 0) {
		throw new Error(`[Pulse] Invalid callback debounce delay: ${value}`);
	}
	return delay;
}

type ElementMeta = {
	eval?: Set<string>;
	path?: string;
	callbacks?: Map<string, CallbackEntry>;
};

export class VDOMRenderer {
	#client: PulseSocketIOClient;
	#path: string;
	#registry: ComponentRegistry;

	// Track callback entries for teardown.
	#callbackEntries: Set<CallbackEntry>;

	// Track eval keys + callback entries per ReactElement (not real props).
	#metaMap: WeakMap<ReactElement, ElementMeta>;

	constructor(client: PulseSocketIOClient, path: string, registry: ComponentRegistry = {}) {
		this.#client = client;
		this.#path = path;
		this.#registry = registry;
		this.#callbackEntries = new Set();
		this.#metaMap = new WeakMap();
	}

	getObject(key: string): unknown {
		const obj = (this.#registry as any)[key];
		if (obj === undefined) {
			throw new Error(`[Pulse] Unknown registry key: ${key}`);
		}
		return obj;
	}

	#resolveIdentifier(name: string): unknown {
		const v = (globalThis as any)[name];
		if (v === undefined) {
			throw new Error(`[Pulse] Unknown identifier in expr: ${name}`);
		}
		return v;
	}

	#evalExpr(expr: VDOMNode, env: Env): unknown {
		// Handle primitives directly (wire format optimization)
		if (expr === null || typeof expr !== "object") {
			return expr;
		}
		// Handle VDOMElement (has "tag" instead of "t")
		if ("tag" in expr) {
			return this.renderNode(expr, "");
		}
		switch (expr.t) {
			case "ref":
				return this.getObject(expr.key);
			case "id":
				if (Object.hasOwn(env, expr.name)) return env[expr.name];
				return this.#resolveIdentifier(expr.name);
			case "lit":
				return expr.value;
			case "undef":
				return undefined;
			case "array": {
				const out: unknown[] = [];
				for (const it of expr.items) {
					out.push(this.#evalExpr(it, env));
				}
				return out;
			}
			case "object": {
				const out: Record<string, unknown> = {};
				for (const [k, vexpr] of Object.entries(expr.props)) {
					out[k] = this.#evalExpr(vexpr, env);
				}
				return out;
			}
			case "member": {
				const obj = this.#evalExpr(expr.obj, env) as any;
				return obj?.[expr.prop];
			}
			case "sub": {
				const obj = this.#evalExpr(expr.obj, env) as any;
				const key = this.#evalExpr(expr.key, env) as any;
				return obj?.[key];
			}
			case "call": {
				const fn = this.#evalExpr(expr.callee, env) as any;
				const args = expr.args.map((a) => this.#evalExpr(a, env));
				if (typeof fn !== "function") throw new Error("[Pulse] call callee is not a function");
				return fn(...args);
			}
			case "unary": {
				const v = this.#evalExpr(expr.arg, env) as any;
				switch (expr.op) {
					case "!":
						return !v;
					case "+":
						return +v;
					case "-":
						return -v;
					case "typeof":
						return typeof v;
					case "void":
						return void v;
					default:
						throw new Error(`[Pulse] Unsupported unary op: ${expr.op}`);
				}
			}
			case "binary": {
				const l = this.#evalExpr(expr.left, env) as any;
				const r = this.#evalExpr(expr.right, env) as any;
				switch (expr.op) {
					case "+":
						return l + r;
					case "-":
						return l - r;
					case "*":
						return l * r;
					case "/":
						return l / r;
					case "%":
						return l % r;
					case "&&":
						return l && r;
					case "||":
						return l || r;
					case "??":
						return l ?? r;
					case "**":
						return l ** r;
					case "in":
						return l in r;
					case "instanceof":
						return l instanceof r;
					case "===":
						return l === r;
					case "!==":
						return l !== r;
					case "<":
						return l < r;
					case "<=":
						return l <= r;
					case ">":
						return l > r;
					case ">=":
						return l >= r;
					default:
						throw new Error(`[Pulse] Unsupported binary op: ${expr.op}`);
				}
			}
			case "ternary":
				return this.#evalExpr(expr.cond, env)
					? this.#evalExpr(expr.then, env)
					: this.#evalExpr(expr.else_, env);
			case "template": {
				let s = "";
				for (const part of expr.parts) {
					if (typeof part === "string") s += part;
					else s += String(this.#evalExpr(part, env));
				}
				return s;
			}
			case "arrow": {
				const params = expr.params;
				return (...args: unknown[]) => {
					const nextEnv: Env = { ...env };
					for (let i = 0; i < params.length; i += 1) nextEnv[params[i]!] = args[i];
					return this.#evalExpr(expr.body, nextEnv);
				};
			}
			case "new": {
				const Ctor = this.#evalExpr(expr.ctor, env) as any;
				const args = expr.args.map((a) => this.#evalExpr(a, env));
				return new Ctor(...args);
			}
			default:
				throw new Error(`[Pulse] Unknown expr node: ${(expr as any).t}`);
		}
	}

	#propPath(path: string, prop: string) {
		return path ? `${path}.${prop}` : prop;
	}

	#clearPending(entry: CallbackEntry) {
		if (entry.timer) {
			clearTimeout(entry.timer);
		}
		entry.timer = null;
		entry.lastArgs = null;
		entry.dueAt = null;
	}

	#firePending(entry: CallbackEntry, fire: (args: any[]) => void) {
		const args = entry.lastArgs;
		this.#clearPending(entry);
		if (!args) return;
		fire(args);
	}

	#scheduleDebounced(
		entry: CallbackEntry,
		delayMs: number,
		args: any[],
		fire: (args: any[]) => void,
	) {
		if (entry.timer) clearTimeout(entry.timer);
		entry.lastArgs = args;
		entry.dueAt = Date.now() + delayMs;
		entry.timer = setTimeout(() => {
			this.#firePending(entry, fire);
		}, delayMs);
	}

	#dropCallback(meta: ElementMeta, prop: string) {
		const callbacks = meta.callbacks;
		if (!callbacks) return;
		const entry = callbacks.get(prop);
		if (!entry) return;
		this.#clearPending(entry);
		this.#callbackEntries.delete(entry);
		callbacks.delete(prop);
		if (callbacks.size === 0) {
			meta.callbacks = undefined;
		}
	}

	#ensureCallbackEntry(meta: ElementMeta, prop: string): CallbackEntry {
		if (!meta.callbacks) {
			meta.callbacks = new Map();
		}
		const callbacks = meta.callbacks;
		let entry = callbacks.get(prop);
		if (!entry) {
			const fire = (args: any[]) => {
				const key = this.#propPath(meta.path ?? "", prop);
				this.#client.invokeCallback(this.#path, key, args);
			};
			entry = {
				fn: (...args: any[]) => {
					if (entry!.delayMs == null) {
						fire(args);
						return;
					}
					const callArgs = args.map(extractEvent);
					this.#scheduleDebounced(entry!, entry!.delayMs, callArgs, fire);
				},
				delayMs: null,
				timer: null,
				lastArgs: null,
				dueAt: null,
			};
			callbacks.set(prop, entry);
			this.#callbackEntries.add(entry);
		}
		return entry;
	}

	#dropCallbacksInSubtree(node: ReactNode, path: string) {
		if (node == null || typeof node === "boolean" || typeof node === "number" || typeof node === "string") {
			return;
		}
		if (Array.isArray(node)) {
			for (let i = 0; i < node.length; i += 1) {
				const childPath = path ? `${path}.${i}` : String(i);
				this.#dropCallbacksInSubtree(node[i], childPath);
			}
			return;
		}
		if (!isValidElement(node)) return;
		const element = node as ReactElement<Record<string, any> | null>;
		const meta = this.#metaMap.get(element);
		const basePath = meta?.path ?? path;
		const callbacks = meta?.callbacks;
		if (callbacks && callbacks.size > 0) {
			for (const entry of callbacks.values()) {
				this.#clearPending(entry);
				this.#callbackEntries.delete(entry);
			}
			callbacks.clear();
			meta!.callbacks = undefined;
		}
		const baseProps = (element.props ?? {}) as Record<string, any>;
		for (const key of Object.keys(baseProps)) {
			if (key === "children") continue;
			const v = baseProps[key];
			this.#dropCallbacksInSubtree(v, this.#propPath(basePath, key));
		}
		const children = this.#ensureChildrenArray(element);
		for (let i = 0; i < children.length; i += 1) {
			const childPath = basePath ? `${basePath}.${i}` : String(i);
			this.#dropCallbacksInSubtree(children[i], childPath);
		}
	}

	#getCallback(meta: ElementMeta, prop: string, delayMs: CallbackDelay) {
		const entry = this.#ensureCallbackEntry(meta, prop);
		if (entry.delayMs !== delayMs) {
			entry.delayMs = delayMs;
		}
		return entry.fn;
	}

	#transformEvalProp(path: string, meta: ElementMeta, prop: string, value: VDOMPropValue) {
		const cbDelay = parseCallbackPlaceholder(value);
		if (cbDelay !== undefined) return this.#getCallback(meta, prop, cbDelay);
		if (isExprNode(value)) return this.#evalExpr(value, {});
		if (typeof value === "object" && value !== null && "tag" in value) {
			// Render-prop subtree; traverse as a prop path segment (non-numeric).
			return this.renderNode(value as VDOMNode, this.#propPath(path, prop));
		}
		// Eval-marked but still JSON => pass through.
		return value as JsonValue;
	}

	#rememberMeta(el: ReactElement, meta: ElementMeta) {
		this.#metaMap.set(el, meta);
		return el;
	}

	clearPendingCallbacks() {
		for (const entry of Array.from(this.#callbackEntries)) {
			this.#clearPending(entry);
		}
		// Keep entries so StrictMode cleanup (no real unmount) can still cancel
		// future debounced calls on the reused renderer instance.
	}

	renderNode(node: VDOMNode, currentPath = ""): ReactNode {
		// primitives
		if (node == null || typeof node === "boolean" || typeof node === "number") return node;
		if (typeof node === "string") return node;

		// expr
		if (isExprNode(node)) return this.#evalExpr(node, {}) as ReactNode;

		// element
		if (isElementNode(node)) {
			const { tag, props = {}, children = [], eval: evalKeys } = node;
			// 1. Resolve component
			let component: React.ComponentType<any> | string;
			if (typeof tag === "string") {
				if (tag.startsWith(REF_PREFIX)) {
					const key = tag.slice(REF_PREFIX.length);
					component = this.#registry[key] as React.ComponentType<any>;

					if (!component) {
						throw new Error(`[Pulse] Missing component '${key}'`);
					}
				} else {
					component = tag.length > 0 ? tag : Fragment;
				}
			} else {
				component = this.#evalExpr(tag, {}) as any;
			}
			// 2. Build props
			const newProps: Record<string, any> = {};
			let evalSet: Set<string> | undefined;
			const meta: ElementMeta = { path: currentPath };
			if (!evalKeys) {
				// Hot path: no eval -> props are plain JSON; copy as-is.
				for (const [propName, propValue] of Object.entries(props)) {
					newProps[propName] = propValue;
				}
			} else {
				evalSet = new Set(evalKeys);
				meta.eval = evalSet;
				for (const [propName, propValue] of Object.entries(props)) {
					if (!evalSet.has(propName)) {
						newProps[propName] = propValue;
						continue;
					}
					newProps[propName] = this.#transformEvalProp(
						currentPath,
						meta,
						propName,
						propValue,
					);
				}
			}
			if (node.key) newProps.key = node.key;

			// 3. Render children
			const renderedChildren: ReactNode[] = [];
			for (let i = 0; i < children.length; i += 1) {
				const child = children[i]!;
				const childPath = currentPath ? `${currentPath}.${i}` : String(i);
				renderedChildren.push(this.renderNode(child, childPath));
			}

			try {
				return this.#rememberMeta(
					createElement(component, newProps, ...renderedChildren),
					meta,
				);
			} catch (error) {
				console.error("[Pulse] Failed to create element:", node)
				throw error;
			}
		}

		if (process.env.NODE_ENV !== "production") {
			console.error("Unknown VDOM node:", node);
		}
		return null;
	}

	init(view: PulsePrerenderView & { vdom: VDOM }): ReactNode {
		return this.renderNode(view.vdom);
	}

	/**
	 * Evaluate a VDOMNode expression (for run_js support).
	 */
	evaluateExpr(expr: VDOMNode): unknown {
		return this.#evalExpr(expr, {});
	}

	#ensureChildrenArray(el: ReactElement): ReactNode[] {
		const children = (el.props as any)?.children as ReactNode | undefined;
		if (children == null) return [];
		return Array.isArray(children) ? children.slice() : [children];
	}

	#cloneWithMeta(prev: ReactElement, next: ReactElement) {
		const meta = this.#metaMap.get(prev);
		if (meta) this.#metaMap.set(next, meta);
		return next;
	}

	// Update paths within a subtree after a move so callbacks resolve correctly.
	#rebindCallbacksInSubtree(node: ReactNode, path: string): ReactNode {
		if (node == null || typeof node === "boolean" || typeof node === "number" || typeof node === "string") {
			return node;
		}
		if (Array.isArray(node)) {
			for (let i = 0; i < node.length; i += 1) {
				const childPath = path ? `${path}.${i}` : String(i);
				this.#rebindCallbacksInSubtree(node[i], childPath);
			}
			return node;
		}
		if (!isValidElement(node)) return node;
		const element = node as ReactElement<Record<string, any> | null>;
		const meta = this.#metaMap.get(element);
		if (meta) {
			meta.path = path;
		} else {
			this.#metaMap.set(element, { path });
		}

		const baseProps = (element.props ?? {}) as Record<string, any>;
		for (const key of Object.keys(baseProps)) {
			if (key === "children") continue;
			const v = baseProps[key];
			this.#rebindCallbacksInSubtree(v, this.#propPath(path, key));
		}

		const children = this.#ensureChildrenArray(element);
		for (let i = 0; i < children.length; i += 1) {
			const childPath = path ? `${path}.${i}` : String(i);
			this.#rebindCallbacksInSubtree(children[i], childPath);
		}

		return node;
	}

	applyUpdates(initialTree: ReactNode, updates: VDOMUpdate[]): ReactNode {
		let newTree: ReactNode = initialTree;
		for (const update of updates) {
			const parts = update.path.split(".").filter((s) => s.length > 0);

			const descend = (node: ReactNode, depth: number, path: string): ReactNode => {
				if (depth < parts.length) {
					this.#assertIsElement(node, parts, depth);
					const element = node as ReactElement<Record<string, any> | null>;
					const childKey = parts[depth]!;
					const childIdx = +childKey;
					const childPath = path ? `${path}.${childKey}` : childKey;
					if (!Number.isNaN(childIdx)) {
						const childrenArr = this.#ensureChildrenArray(element);
						const child = childrenArr[childIdx];
						childrenArr[childIdx] = descend(child, depth + 1, childPath) as any;
						return this.#cloneWithMeta(element, cloneElement(element, undefined, ...childrenArr));
					} else {
						const baseProps = (element.props ?? {}) as Record<string, any>;
						const child = baseProps[childKey];
						const props = { ...baseProps, [childKey]: descend(child, depth + 1, childPath) };
						return this.#cloneWithMeta(element, cloneElement(element, props));
					}
				}

				switch (update.type) {
					case "replace":
						this.#dropCallbacksInSubtree(node, path);
						return this.renderNode(update.data, update.path);

					case "update_props": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const currentProps = (element.props ?? {}) as Record<string, any>;
						const nextProps: Record<string, any> = { ...currentProps };

						const prevMeta = this.#metaMap.get(element);
						const meta: ElementMeta = prevMeta ?? {};
						const prevEval = meta.eval;
						const prevPath = prevMeta?.path ?? path;
						const evalPatch = update.data.eval;
						const nextEval: Set<string> | undefined =
							evalPatch === undefined
								? prevEval
								: evalPatch.length === 0
									? undefined
									: new Set(evalPatch);
						const evalCleared = evalPatch !== undefined && evalPatch.length === 0;

						// Drop callbacks that are no longer eval-bound.
						if (nextEval && meta.callbacks) {
							for (const k of Array.from(meta.callbacks.keys())) {
								if (!nextEval.has(k)) {
									this.#dropCallback(meta, k);
								}
							}
						}
						if (evalCleared && meta.callbacks) {
							for (const k of Array.from(meta.callbacks.keys())) {
								delete nextProps[k];
								this.#dropCallback(meta, k);
							}
						}

						if (update.data.remove && update.data.remove.length > 0) {
							for (const key of update.data.remove) {
								const removedValue = currentProps[key];
								if (removedValue !== undefined) {
									this.#dropCallbacksInSubtree(removedValue, this.#propPath(prevPath, key));
								}
								delete nextProps[key];
								if (meta.callbacks?.has(key)) {
									this.#dropCallback(meta, key);
								}
							}
						}
						if (update.data.set) {
							for (const [k, v] of Object.entries(update.data.set)) {
								const prevValue = currentProps[k];
								if (prevValue !== undefined) {
									this.#dropCallbacksInSubtree(prevValue, this.#propPath(prevPath, k));
								}
								// Only interpret eval-marked keys; otherwise treat as JSON.
								const isEval = nextEval?.has(k) === true;
								const cbDelay = isEval ? parseCallbackPlaceholder(v) : undefined;
								nextProps[k] = isEval
									? this.#transformEvalProp(path, meta, k, v as any)
									: (v as any);
								if (cbDelay === undefined && meta.callbacks?.has(k)) {
									this.#dropCallback(meta, k);
								}
							}
						}
						meta.eval = nextEval;
						meta.path = path;

						const removedSomething = (update.data.remove?.length ?? 0) > 0;
						if (removedSomething) {
							nextProps.key = (element as any).key;
							nextProps.ref = (element as any).ref;
							return this.#rememberMeta(
								createElement(element.type, nextProps, ...this.#ensureChildrenArray(element)),
								meta,
							);
						} else {
							return this.#rememberMeta(cloneElement(element, nextProps), meta);
						}
					}

					case "reconciliation": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const prevChildren = this.#ensureChildrenArray(element);
						const nextChildren: ReactNode[] = [];

						const [newIndices, newContents] = update.new;
						const [reuseIndices, reuseSources] = update.reuse;
						const newIndexSet = new Set(newIndices);
						const reuseIndexSet = new Set(reuseIndices);
						const reuseSourceSet = new Set(reuseSources);
						for (let i = 0; i < prevChildren.length; i += 1) {
							const reused =
								reuseSourceSet.has(i) ||
								(i < update.N && !newIndexSet.has(i) && !reuseIndexSet.has(i));
							if (!reused) {
								const childPath = path ? `${path}.${i}` : String(i);
								this.#dropCallbacksInSubtree(prevChildren[i], childPath);
							}
						}

						let nextNew = -1,
							nextReuse = -1,
							newIdx = -1,
							reuseIdx = -1;
						if (newIndices.length > 0) {
							nextNew = newIndices[0]!;
							newIdx = 0;
						}
						if (reuseIndices.length > 0) {
							nextReuse = reuseIndices[0]!;
							reuseIdx = 0;
						}

						for (let i = 0; i < update.N; i += 1) {
							if (i === nextNew) {
								const contents = newContents[newIdx]!;
								const childPath = path ? `${path}.${i}` : String(i);
								nextChildren.push(this.renderNode(contents, childPath));
								nextNew = newIdx < newIndices.length - 1 ? newIndices[++newIdx]! : -1;
							} else if (i === nextReuse) {
								const srcIdx = reuseSources[reuseIdx]!;
								let src = prevChildren[srcIdx];
								const childPath = path ? `${path}.${i}` : String(i);
								// If the node moved, callbacks inside need new paths.
								src = this.#rebindCallbacksInSubtree(src, childPath);
								nextChildren.push(src);
								nextReuse = reuseIdx < reuseIndices.length - 1 ? reuseIndices[++reuseIdx]! : -1;
							} else {
								nextChildren.push(prevChildren[i]);
							}
						}
						if (nextChildren.length === 0) {
							nextChildren.push(null);
						}

						return this.#cloneWithMeta(
							element,
							cloneElement(element, null!, ...nextChildren),
						);
					}

					default:
						throw new Error(`[Pulse renderer] Unknown update type: ${(update as any)?.type}`);
				}
			};

			newTree = descend(newTree, 0, "");
		}
		return newTree;
	}

	#assertIsElement(node: ReactNode, parts: string[], depth: number): node is ReactElement {
		if (process.env.NODE_ENV !== "production" && !isValidElement(node)) {
			console.error("Invalid node:", node);
			throw new Error(`Invalid node at path ${parts.slice(0, depth).join(".")}`);
		}
		return true;
	}
}
