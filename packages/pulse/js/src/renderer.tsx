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
	cbKeys?: Set<string>;
	path?: string;
};

export class VDOMRenderer {
	#client: PulseSocketIOClient;
	#path: string;
	#registry: ComponentRegistry;

	// Callback entries keyed by "path.prop"
	#callbacks: Map<string, CallbackEntry>;

	// Track eval keys + callback keys per ReactElement (not real props).
	#metaMap: WeakMap<ReactElement, ElementMeta>;

	constructor(client: PulseSocketIOClient, path: string, registry: ComponentRegistry = {}) {
		this.#client = client;
		this.#path = path;
		this.#registry = registry;
		this.#callbacks = new Map();
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

	#clearCallback(key: string) {
		const entry = this.#callbacks.get(key);
		if (!entry) return;
		if (entry.timer) clearTimeout(entry.timer);
		this.#callbacks.delete(key);
	}

	#flushCallback(key: string) {
		const entry = this.#callbacks.get(key);
		if (!entry) return;
		if (entry.timer) {
			clearTimeout(entry.timer);
			entry.timer = null;
		}
		if (entry.delayMs != null && entry.lastArgs != null) {
			const latestArgs = entry.lastArgs;
			entry.lastArgs = null;
			this.#client.invokeCallback(this.#path, key, latestArgs);
		}
		this.#callbacks.delete(key);
	}

	#ensureCallbackEntry(key: string): CallbackEntry {
		let entry = this.#callbacks.get(key);
		if (!entry) {
			entry = {
				fn: (...args: any[]) => {
					if (entry!.delayMs == null) {
						this.#client.invokeCallback(this.#path, key, args);
						return;
					}
					const callArgs = args.map(extractEvent);
					entry!.lastArgs = callArgs;
					if (entry!.timer) clearTimeout(entry!.timer);
					entry!.timer = setTimeout(() => {
						entry!.timer = null;
						const latestArgs = entry!.lastArgs ?? [];
						entry!.lastArgs = null;
						this.#client.invokeCallback(this.#path, key, latestArgs);
					}, entry!.delayMs);
				},
				delayMs: null,
				timer: null,
				lastArgs: null,
			};
			this.#callbacks.set(key, entry);
		}
		return entry;
	}

	#flushCallbacksInSubtree(node: ReactNode, path: string) {
		if (node == null || typeof node === "boolean" || typeof node === "number" || typeof node === "string") {
			return;
		}
		if (Array.isArray(node)) {
			for (let i = 0; i < node.length; i += 1) {
				const childPath = path ? `${path}.${i}` : String(i);
				this.#flushCallbacksInSubtree(node[i], childPath);
			}
			return;
		}
		if (!isValidElement(node)) return;
		const element = node as ReactElement<Record<string, any> | null>;
		const meta = this.#metaMap.get(element);
		const cbKeys = meta?.cbKeys;
		const basePath = meta?.path ?? path;
		if (cbKeys && cbKeys.size > 0) {
			for (const k of cbKeys) {
				this.#flushCallback(this.#propPath(basePath, k));
			}
		}
		const baseProps = (element.props ?? {}) as Record<string, any>;
		for (const key of Object.keys(baseProps)) {
			if (key === "children") continue;
			const v = baseProps[key];
			if (isValidElement(v)) {
				this.#flushCallbacksInSubtree(v, this.#propPath(basePath, key));
			}
		}
		const children = this.#ensureChildrenArray(element);
		for (let i = 0; i < children.length; i += 1) {
			const childPath = basePath ? `${basePath}.${i}` : String(i);
			this.#flushCallbacksInSubtree(children[i], childPath);
		}
	}

	#getCallback(path: string, prop: string, delayMs: CallbackDelay) {
		const key = this.#propPath(path, prop);
		const entry = this.#ensureCallbackEntry(key);
		if (entry.delayMs !== delayMs) {
			entry.delayMs = delayMs;
		}
		return entry.fn;
	}

	#transformEvalProp(path: string, prop: string, value: VDOMPropValue) {
		const cbDelay = parseCallbackPlaceholder(value);
		if (cbDelay !== undefined) return this.#getCallback(path, prop, cbDelay);
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

	flushPendingCallbacks() {
		for (const key of Array.from(this.#callbacks.keys())) {
			this.#flushCallback(key);
		}
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
			let cbKeys: Set<string> | undefined;
			const newProps: Record<string, any> = {};
			let evalSet: Set<string> | undefined;
			if (!evalKeys) {
				// Hot path: no eval -> props are plain JSON; copy as-is.
				for (const [propName, propValue] of Object.entries(props)) {
					newProps[propName] = propValue;
				}
			} else {
				evalSet = new Set(evalKeys);
				for (const [propName, propValue] of Object.entries(props)) {
					if (!evalSet.has(propName)) {
						newProps[propName] = propValue;
						continue;
					}
					const cbDelay = parseCallbackPlaceholder(propValue);
					if (cbDelay !== undefined) {
						if (!cbKeys) cbKeys = new Set();
						cbKeys.add(propName);
					}
					newProps[propName] = this.#transformEvalProp(currentPath, propName, propValue);
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
					{ eval: evalSet, cbKeys, path: currentPath },
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

	// Rebind callback function props within a subtree after a path-changing move.
	#rebindCallbacksInSubtree(node: ReactNode, path: string): ReactNode {
		if (!isValidElement(node)) return node;
		const element = node as ReactElement<Record<string, any> | null>;

		const baseProps = (element.props ?? {}) as Record<string, any>;
		const nextProps: Record<string, any> = { ...baseProps };

		const meta = this.#metaMap.get(element);
		const cbKeys = meta?.cbKeys;
		const prevPath = meta?.path ?? path;
		if (cbKeys && cbKeys.size > 0) {
			for (const k of cbKeys) {
				const oldKey = this.#propPath(prevPath, k);
				const newKey = this.#propPath(path, k);
				const delay = this.#callbacks.get(oldKey)?.delayMs ?? null;
				if (oldKey !== newKey) this.#clearCallback(oldKey);
				nextProps[k] = this.#getCallback(path, k, delay);
			}
		}
		for (const key of Object.keys(baseProps)) {
			const v = baseProps[key];
			if (isValidElement(v)) {
				nextProps[key] = this.#rebindCallbacksInSubtree(v, this.#propPath(path, key));
			}
		}

		const children = this.#ensureChildrenArray(element).map((child, idx) => {
			const childPath = path ? `${path}.${idx}` : String(idx);
			return this.#rebindCallbacksInSubtree(child, childPath);
		});

		const nextMeta = meta ? { ...meta, path } : { path };
		return this.#rememberMeta(cloneElement(element, nextProps, ...children), nextMeta);
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
						this.#flushCallbacksInSubtree(node, path);
						return this.renderNode(update.data, update.path);

					case "update_props": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const currentProps = (element.props ?? {}) as Record<string, any>;
						const nextProps: Record<string, any> = { ...currentProps };

						const prevMeta = this.#metaMap.get(element);
						const prevEval = prevMeta?.eval;
						const prevCbKeys = prevMeta?.cbKeys;
						const prevPath = prevMeta?.path ?? path;
						const evalPatch = update.data.eval;
						const nextEval: Set<string> | undefined =
							evalPatch === undefined
								? prevEval
								: evalPatch.length === 0
									? undefined
									: new Set(evalPatch);
						const evalCleared = evalPatch !== undefined && evalPatch.length === 0;

						// Maintain callback-keys metadata incrementally (for path rebinding after moves).
						// If eval is cleared, callbacks must disappear unless explicitly re-set.
						let nextCbKeys: Set<string> | undefined;
						if (nextEval) {
							const cbSet = new Set<string>();
							if (prevCbKeys) {
								for (const k of prevCbKeys) {
									if (nextEval.has(k)) {
										cbSet.add(k);
									} else {
										this.#flushCallback(this.#propPath(prevPath, k));
									}
								}
							}
							nextCbKeys = cbSet.size > 0 ? cbSet : undefined;
						}
						if (evalCleared && prevCbKeys) {
							for (const k of prevCbKeys) {
								delete nextProps[k];
								this.#flushCallback(this.#propPath(prevPath, k));
							}
						}

						if (update.data.remove && update.data.remove.length > 0) {
							for (const key of update.data.remove) {
								const removedValue = currentProps[key];
								if (removedValue !== undefined) {
									this.#flushCallbacksInSubtree(removedValue, this.#propPath(prevPath, key));
								}
								delete nextProps[key];
								if (prevCbKeys?.has(key)) {
									this.#flushCallback(this.#propPath(prevPath, key));
								}
								nextCbKeys?.delete(key);
							}
						}
						if (update.data.set) {
							for (const [k, v] of Object.entries(update.data.set)) {
								// Only interpret eval-marked keys; otherwise treat as JSON.
								const isEval = nextEval?.has(k) === true;
								const cbDelay = isEval ? parseCallbackPlaceholder(v) : undefined;
								nextProps[k] = isEval ? this.#transformEvalProp(path, k, v as any) : (v as any);

								// Update cbKeys based on placeholder sentinel in the payload.
								if (cbDelay !== undefined) {
									if (!nextCbKeys) nextCbKeys = new Set();
									nextCbKeys.add(k);
								} else {
									nextCbKeys?.delete(k);
									if (prevCbKeys?.has(k)) {
										this.#flushCallback(this.#propPath(prevPath, k));
									}
								}
							}
						}

						if (nextCbKeys && nextCbKeys.size === 0) nextCbKeys = undefined;

						const removedSomething = (update.data.remove?.length ?? 0) > 0;
						if (removedSomething) {
							nextProps.key = (element as any).key;
							nextProps.ref = (element as any).ref;
							return this.#rememberMeta(
								createElement(element.type, nextProps, ...this.#ensureChildrenArray(element)),
								{ eval: nextEval, cbKeys: nextCbKeys, path },
							);
						} else {
							return this.#rememberMeta(cloneElement(element, nextProps), {
								eval: nextEval,
								cbKeys: nextCbKeys,
								path,
							});
						}
					}

					case "reconciliation": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const prevChildren = this.#ensureChildrenArray(element);
						const nextChildren: ReactNode[] = [];

						const [newIndices, newContents] = update.new;
						const [reuseIndices, reuseSources] = update.reuse;

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
