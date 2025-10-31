import {
	type ComponentType,
	cloneElement,
	createElement,
	type FC,
	Fragment,
	isValidElement,
	lazy,
	type PropsWithChildren,
	type ReactElement,
	type ReactNode,
	Suspense,
} from "react";
import type { PulseSocketIOClient } from "./client";
import type { PulsePrerenderView } from "./pulse";
import type { ComponentRegistry, PathDelta, VDOMNode, VDOMUpdate } from "./vdom";
import { FRAGMENT_TAG, isElementNode, isMountPointNode, MOUNT_POINT_PREFIX } from "./vdom";

export class VDOMRenderer {
	#callbacks: Set<string>;
	#callbackCache: Map<string, (...args: any) => void>;
	#renderPropKeys: Set<string>;
	#cssProps: Set<string>;
	#callbackList: string[];
	#client: PulseSocketIOClient;
	#path: string;
	#components: ComponentRegistry;
	#cssModules: Record<string, Record<string, string>>;

	constructor(
		client: PulseSocketIOClient,
		path: string,
		components: ComponentRegistry,
		cssModules: Record<string, Record<string, string>>,
		initialCallbacks: string[] = [],
		initialRenderProps: string[] = [],
		initialCssRefs: string[] = [],
	) {
		this.#client = client;
		this.#path = path;
		this.#components = components;
		this.#cssModules = cssModules;
		this.#callbacks = new Set(initialCallbacks);
		this.#callbackCache = new Map();
		this.#renderPropKeys = new Set(initialRenderProps);
		this.#cssProps = new Set(initialCssRefs);
		this.#callbackList = [...this.#callbacks].sort();
	}

	// Accessors used by update logic to determine which props need rebinding
	hasCallbackPath(path: string) {
		return this.#callbacks.has(path);
	}

	hasRenderPropPath(path: string) {
		return this.#renderPropKeys.has(path);
	}

	hasAnyCallbackUnder(prefix: string): boolean {
		if (prefix === "") return this.#callbackList.length > 0;
		const i = this.#lowerBound(this.#callbackList, prefix);
		return i < this.#callbackList.length && this.#callbackList[i]!.startsWith(prefix);
	}

	applyCallbackDelta(delta: PathDelta) {
		// Only update the internal callback path registry and cache. We rely on
		// accompanying update_props operations that contain the "$cb" placeholder
		// to trigger prop updates; transformValue will resolve to functions.
		if (delta.remove) {
			for (const key of delta.remove) {
				this.#callbacks.delete(key);
				this.#callbackCache.delete(key);
			}
		}
		if (delta.add) {
			for (const key of delta.add) {
				this.#callbacks.add(key);
			}
		}
		this.#callbackList = [...this.#callbacks].sort();
	}

	applyRenderPropsDelta(delta: PathDelta) {
		if (delta.remove) {
			for (const key of delta.remove) {
				this.#renderPropKeys.delete(key);
			}
		}
		if (delta.add) {
			for (const key of delta.add) {
				this.#renderPropKeys.add(key);
			}
		}
	}

	applyCssRefsDelta(delta: PathDelta) {
		if (delta.remove) {
			for (const prop of delta.remove) {
				this.#cssProps.delete(prop);
			}
		}
		if (delta.add) {
			for (const prop of delta.add) {
				this.#cssProps.add(prop);
			}
		}
	}

	getCallback(path: string, prop: string) {
		const key = this.#propPath(path, prop);
		let fn = this.#callbackCache.get(key);
		if (!fn) {
			fn = (...args: any[]) => this.#client.invokeCallback(this.#path, key, args);
			this.#callbackCache.set(key, fn);
		}
		return fn;
	}

	renderNode(node: VDOMNode, currentPath = ""): ReactNode {
		// Handle primitives early
		if (
			node == null || // catches both null and undefined
			typeof node === "boolean" ||
			typeof node === "number" ||
			typeof node === "string"
		) {
			return node;
		}

		// Element nodes
		if (isElementNode(node)) {
			const { tag, props = {}, children = [] } = node;

			const newProps: Record<string, any> = {};
			for (const [propName, propValue] of Object.entries(props)) {
				newProps[propName] = this.transformValue(currentPath, propName, propValue);
			}

			if (node.key) {
				newProps.key = node.key;
			}

			const renderedChildren = [];
			for (let index = 0; index < children.length; index += 1) {
				const child = children[index]!;
				const childPath = currentPath ? `${currentPath}.${index}` : String(index);
				renderedChildren.push(this.renderNode(child, childPath));
			}

			if (isMountPointNode(node)) {
				const componentKey = node.tag.slice(MOUNT_POINT_PREFIX.length);
				const Component = this.#components[componentKey]!;
				if (!Component) {
					throw new Error(
						`Could not find component ${componentKey}. This is a Pulse internal error.`,
					);
				}
				return createElement(Component, newProps, ...renderedChildren);
			}

			return createElement(tag === FRAGMENT_TAG ? Fragment : tag, newProps, ...renderedChildren);
		}

		// Fallback for unknown node types
		if (process.env.NODE_ENV !== "production") {
			console.error("Unknown VDOM node type:", node);
		}
		return null;
	}

	#propPath(path: string, prop: string) {
		return path ? `${path}.${prop}` : prop;
	}

	transformValue(path: string, key: string, value: any) {
		const propPath = this.#propPath(path, key);
		if (this.#callbacks.has(propPath)) {
			return this.getCallback(path, key);
		}
		if (this.#renderPropKeys.has(propPath)) {
			return this.renderNode(value, propPath);
		}
		if (this.#cssProps.has(propPath)) {
			return this.#resolveCssToken(value);
		}
		return value;
	}

	#resolveCssToken(token: string): string {
		const idx = token.indexOf(":");
		if (idx === -1) {
			return token;
		}
		const moduleId = token.slice(0, idx);
		const className = token.slice(idx + 1);
		if (!moduleId || !className) {
			return token;
		}
		const mod = this.#cssModules[moduleId];
		if (!mod) {
			throw new Error(`Received CSS reference for unknown module '${moduleId}'`);
		}
		const resolved = mod[className];
		if (typeof resolved !== "string") {
			throw new Error(
				`Received CSS reference for missing class '${className}' in module '${moduleId}'`,
			);
		}
		return resolved;
	}

	init(view: PulsePrerenderView): ReactNode {
		// Set callbacks
		this.#callbacks = new Set(view.callbacks);
		// prune stale cached callbacks
		for (const k of Array.from(this.#callbackCache.keys())) {
			if (!this.#callbacks.has(k)) this.#callbackCache.delete(k);
		}
		this.#callbackList = [...this.#callbacks].sort();

		// Set render props
		this.#renderPropKeys = new Set(view.render_props);

		// Set CSS refs
		this.#cssProps = new Set(view.css_refs);

		return this.renderNode(view.vdom);
	}

	#ensureChildrenArray(el: ReactElement): ReactNode[] {
		const children = (el.props as any)?.children as ReactNode | undefined;
		if (children == null) return [];
		return Array.isArray(children) ? children.slice() : [children];
	}

	applyUpdates(initialTree: ReactNode, updates: VDOMUpdate[]): ReactNode {
		let newTree: ReactNode = initialTree;
		for (const update of updates) {
			if (update.type === "update_callbacks") {
				this.applyCallbackDelta(update.data);
				continue;
			}
			if (update.type === "update_css_refs") {
				this.applyCssRefsDelta(update.data);
				continue;
			}
			if (update.type === "update_render_props") {
				this.applyRenderPropsDelta(update.data);
				continue;
			}

			const parts = update.path.split(".").filter((s) => s.length > 0);

			const descend = (node: ReactNode, depth: number, path: string): ReactNode => {
				if (depth < parts.length) {
					this.#assertIsElement(node, parts, depth);
					const element = node as ReactElement<Record<string, any> | null>;
					const childKey = parts[depth]!;
					const childIdx = +childKey;
					const childPath = path ? `${path}.${childKey}` : childKey;
					if (!Number.isNaN(childIdx)) {
						// Regular child traversal
						const childrenArr = this.#ensureChildrenArray(element);
						const child = childrenArr[childIdx];
						childrenArr[childIdx] = descend(child, depth + 1, childPath) as any;
						return cloneElement(element, undefined, ...childrenArr);
					} else {
						// Render prop traversal
						const baseProps = (element.props ?? {}) as Record<string, any>;
						const child = baseProps[childKey];
						const props = {
							...baseProps,
							[childKey]: descend(child, depth + 1, childPath),
						};
						return cloneElement(element, props);
					}
				}
				switch (update.type) {
					case "replace": {
						return this.renderNode(update.data, update.path);
					}
					case "update_props": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const currentProps = (element.props ?? {}) as Record<string, any>;
						const nextProps: Record<string, any> = { ...currentProps };
						const delta = update.data;
						if (delta.remove && delta.remove.length > 0) {
							for (const key of delta.remove) {
								if (key in nextProps) {
									delete nextProps[key];
								}
							}
						}
						if (delta.set) {
							for (const [k, v] of Object.entries(delta.set)) {
								nextProps[k] = this.transformValue(path, k, v);
							}
						}

						// If some props were removed, use `createElement` to fully override
						// the props, as `cloneElement` shallowly merges the new props with
						// the old ones.
						const removedSomething = (delta.remove?.length ?? 0) > 0;
						if (removedSomething) {
							// Preserve key + ref
							nextProps.key = element.key;
							nextProps.ref = (element as any).ref;
							return createElement(element.type, nextProps, ...this.#ensureChildrenArray(element));
						} else {
							// Don't touch children. Key and ref are transferred by cloneElement.
							return cloneElement(element, nextProps);
						}
					}
					case "reconciliation": {
						this.#assertIsElement(node, parts, depth);
						const element = node as ReactElement;
						const prevChildren = this.#ensureChildrenArray(element);
						const nextChildren = [];

						const [newIndices, newContents] = update.new;
						const [reuseIndices, reuseSources] = update.reuse;

						let nextNew = -1,
							nextReuse = -1,
							newIdx = -1,
							reuseIdx = -1;
						if (newIndices.length > 0) {
							nextNew = newIndices[0];
							newIdx = 0;
						}
						if (reuseIndices.length > 0) {
							nextReuse = reuseIndices[0];
							reuseIdx = 0;
						}
						for (let i = 0; i < update.N; ++i) {
							if (i === nextNew) {
								const contents = newContents[newIdx];
								const childPath = path ? `${path}.${i}` : String(i);
								nextChildren.push(this.renderNode(contents, childPath));
								nextNew = newIdx < newIndices.length - 1 ? newIndices[++newIdx] : -1;
							} else if (i === nextReuse) {
								const srcIdx = reuseSources[reuseIdx];
								let src = prevChildren[srcIdx];
								const childPath = path ? `${path}.${i}` : String(i);
								// The node may have callbacks that need to be updated for this new path
								if (this.hasAnyCallbackUnder(childPath)) {
									src = this.#rebindCallbacksInSubtree(src, childPath);
								}
								nextChildren.push(src);
								nextReuse = reuseIdx < reuseIndices.length - 1 ? reuseIndices[++reuseIdx] : -1;
							} else {
								// No need to rebind callbacks, the node hasn't moved
								nextChildren.push(prevChildren[i]);
							}
						}
						// Pass null to reuse previous props
						return cloneElement(element, null!, ...nextChildren);
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

	// Rebind callback function props within a subtree after a path-changing move
	#rebindCallbacksInSubtree(node: ReactNode, path: string): ReactNode {
		if (!isValidElement(node)) return node;
		const element = node as ReactElement<Record<string, any> | null>;
		const baseProps = (element.props ?? {}) as Record<string, any>;
		const nextProps: Record<string, any> = { ...baseProps };

		// Rebind only callback props; CSS refs are path-agnostic and render-props
		// are handled by the server-side renderer via explicit updates
		for (const key of Object.keys(baseProps)) {
			const propPath = path ? `${path}.${key}` : key;
			if (this.hasCallbackPath(propPath)) {
				nextProps[key] = this.getCallback(path, key);
			}
			if (this.hasRenderPropPath(propPath) && this.hasAnyCallbackUnder(propPath)) {
				nextProps[key] = this.#rebindCallbacksInSubtree(baseProps[key], propPath);
			}
		}

		const children = this.#ensureChildrenArray(element).map((child, idx) => {
			const childPath = path ? `${path}.${idx}` : String(idx);
			if (this.hasAnyCallbackUnder(childPath)) {
				return this.#rebindCallbacksInSubtree(child, childPath);
			} else {
				return child;
			}
		});

		return cloneElement(element, nextProps, ...children);
	}

	// Binary-search lower bound for prefix matching on sorted callback paths
	#lowerBound(arr: string[], target: string): number {
		let lo = 0;
		let hi = arr.length;
		while (lo < hi) {
			const mid = (lo + hi) >>> 1;
			if (arr[mid]! < target) {
				lo = mid + 1;
			} else {
				hi = mid;
			}
		}
		return lo;
	}
}

// The `component` prop should be something like `() =>
// import('~/path/to/component') (we'll need to remap if we're importing a named export and not the default)
export function RenderLazy(
	component: () => Promise<{ default: ComponentType<any> }>,
	fallback?: ReactNode,
): FC<PropsWithChildren<unknown>> {
	const Component = lazy(component);
	return ({ children, ...props }: PropsWithChildren<unknown>) => {
		return (
			<Suspense fallback={fallback}>
				<Component {...props}>{children}</Component>
			</Suspense>
		);
	};
}
