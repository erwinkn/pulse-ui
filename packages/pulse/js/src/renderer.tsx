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

function isCallbackPlaceholder(v: unknown): v is "$cb" {
	return v === "$cb";
}

type ElementMeta = {
	eval?: Set<string>;
	cbKeys?: Set<string>;
};

type UpdateSource = "server" | "local";

export class VDOMRenderer {
	#client: PulseSocketIOClient;
	#path: string;
	#registry: ComponentRegistry;

	// Cache callback functions keyed by "path.prop"
	#callbackCache: Map<string, (...args: any[]) => void>;

	// Track eval keys + callback keys per ReactElement (not real props).
	#metaMap: WeakMap<ReactElement, ElementMeta>;
	#inputOverrides: Map<string, unknown>;
	#localUpdateHandler: ((update: VDOMUpdate) => void) | null = null;

	constructor(client: PulseSocketIOClient, path: string, registry: ComponentRegistry = {}) {
		this.#client = client;
		this.#path = path;
		this.#registry = registry;
		this.#callbackCache = new Map();
		this.#metaMap = new WeakMap();
		this.#inputOverrides = new Map();
	}

	setLocalUpdateHandler(handler: ((update: VDOMUpdate) => void) | null) {
		this.#localUpdateHandler = handler;
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

	#recordInputOverride(path: string, evt: any) {
		const nextValue = evt?.target?.value;
		if (nextValue === undefined) return;
		this.#inputOverrides.set(path, nextValue);
	}

	#applyInputOverride(
		path: string,
		elementType: unknown,
		props: Record<string, any>,
		source: UpdateSource,
	): void {
		if (typeof elementType !== "string") return;
		if (elementType !== "input" && elementType !== "textarea" && elementType !== "select") {
			return;
		}
		if (!Object.hasOwn(props, "value")) {
			this.#inputOverrides.delete(path);
			return;
		}
		const override = this.#inputOverrides.get(path);
		if (override === undefined) return;
		const serverValue = props.value;
		if (override === serverValue) {
			if (source === "server") {
				this.#inputOverrides.delete(path);
			}
			return;
		}
		if (typeof override === "string" && typeof serverValue === "string") {
			if (override.startsWith(serverValue)) {
				props.value = override;
				return;
			}
			if (source === "server") {
				this.#inputOverrides.delete(path);
			}
			return;
		}
		props.value = override;
	}

	#getCallback(path: string, prop: string) {
		const key = this.#propPath(path, prop);
		let fn = this.#callbackCache.get(key);
		if (!fn) {
			fn = (...args: any[]) => {
				if (prop === "onChange" || prop === "onInput") {
					this.#recordInputOverride(path, args[0]);
					const nextValue = args[0]?.target?.value;
					if (nextValue !== undefined) {
						this.#localUpdateHandler?.({
							type: "update_props",
							path,
							data: { set: { value: nextValue } },
						});
					}
				}
				if (prop === "onBlur") {
					this.#inputOverrides.delete(path);
				}
				this.#client.invokeCallback(this.#path, key, args);
			};
			this.#callbackCache.set(key, fn);
		}
		return fn;
	}

	#transformEvalProp(path: string, prop: string, value: VDOMPropValue) {
		if (isCallbackPlaceholder(value)) return this.#getCallback(path, prop);
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
					if (propValue === "$cb") {
						if (!cbKeys) cbKeys = new Set();
						cbKeys.add(propName);
					}
					newProps[propName] = this.#transformEvalProp(currentPath, propName, propValue);
				}
			}
			if (node.key) newProps.key = node.key;
			this.#applyInputOverride(currentPath, component, newProps, "server");

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
					{ eval: evalSet, cbKeys },
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
		if (cbKeys && cbKeys.size > 0) {
			for (const k of cbKeys) {
				nextProps[k] = this.#getCallback(path, k);
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

		return this.#cloneWithMeta(element, cloneElement(element, nextProps, ...children));
	}

	applyUpdates(
		initialTree: ReactNode,
		updates: VDOMUpdate[],
		source: UpdateSource = "server",
	): ReactNode {
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
						return this.renderNode(update.data, update.path);

					case "update_props": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const currentProps = (element.props ?? {}) as Record<string, any>;
						const nextProps: Record<string, any> = { ...currentProps };

						const prevMeta = this.#metaMap.get(element);
						const prevEval = prevMeta?.eval;
						const prevCbKeys = prevMeta?.cbKeys;
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
									if (nextEval.has(k)) cbSet.add(k);
								}
							}
							nextCbKeys = cbSet;
						}
						if (evalCleared && prevCbKeys) {
							for (const k of prevCbKeys) delete nextProps[k];
						}

						if (update.data.remove && update.data.remove.length > 0) {
							for (const key of update.data.remove) {
								delete nextProps[key];
								nextCbKeys?.delete(key);
							}
						}
						if (update.data.set) {
							for (const [k, v] of Object.entries(update.data.set)) {
								// Only interpret eval-marked keys; otherwise treat as JSON.
								const isEval = nextEval?.has(k) === true;
								nextProps[k] = isEval ? this.#transformEvalProp(path, k, v as any) : (v as any);

								// Update cbKeys based on placeholder sentinel in the payload.
								if (nextCbKeys) {
									if (isEval && v === "$cb") nextCbKeys.add(k);
									else nextCbKeys.delete(k);
								}
							}
						}

						if (nextCbKeys && nextCbKeys.size === 0) nextCbKeys = undefined;
						this.#applyInputOverride(path, element.type, nextProps, source);

						const removedSomething = (update.data.remove?.length ?? 0) > 0;
						if (removedSomething) {
							nextProps.key = (element as any).key;
							nextProps.ref = (element as any).ref;
							return this.#rememberMeta(
								createElement(element.type, nextProps, ...this.#ensureChildrenArray(element)),
								{ eval: nextEval, cbKeys: nextCbKeys },
							);
						} else {
							return this.#rememberMeta(cloneElement(element, nextProps), {
								eval: nextEval,
								cbKeys: nextCbKeys,
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

						return this.#cloneWithMeta(element, cloneElement(element, null!, ...nextChildren));
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
