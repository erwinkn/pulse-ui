import React, {
  cloneElement,
  createElement,
  isValidElement,
  lazy,
  Suspense,
  type ComponentType,
} from "react";
import type { ComponentRegistry, VDOMNode, VDOMUpdate, VDOM } from "./vdom";
import {
  FRAGMENT_TAG,
  isElementNode,
  isMountPointNode,
  MOUNT_POINT_PREFIX,
} from "./vdom";
import type { PulseSocketIOClient } from "./client";

export class VDOMRenderer {
  private callbacks: Set<string>;
  private callbackCache: Map<string, Function>;
  private renderPropKeys: Set<string>;
  private cssProps: Set<string>;
  private callbackList: string[];
  constructor(
    private client: PulseSocketIOClient,
    private path: string,
    private components: ComponentRegistry,
    private cssModules: Record<string, Record<string, string>>,
    initialCallbacks: string[] = [],
    initialRenderProps: string[] = [],
    initialCssRefs: string[] = []
  ) {
    console.log("Creating renderer");
    this.callbacks = new Set(initialCallbacks);
    this.callbackCache = new Map();
    this.renderPropKeys = new Set(initialRenderProps);
    this.cssProps = new Set(initialCssRefs);
    this.callbackList = [...this.callbacks].sort();
  }

  // Accessors used by update logic to determine which props need rebinding
  hasCallbackPath(path: string) {
    return this.callbacks.has(path);
  }

  hasRenderPropPath(path: string) {
    return this.renderPropKeys.has(path);
  }

  hasAnyCallbackUnder(prefix: string): boolean {
    if (prefix === "") return this.callbackList.length > 0;
    const i = lowerBound(this.callbackList, prefix);
    return (
      i < this.callbackList.length && this.callbackList[i]!.startsWith(prefix)
    );
  }

  setCallbacks(keys: string[]) {
    this.callbacks = new Set(keys);
    // prune stale cached callbacks
    for (const k of Array.from(this.callbackCache.keys())) {
      if (!this.callbacks.has(k)) this.callbackCache.delete(k);
    }
    this.callbackList = [...this.callbacks].sort();
  }

  setRenderProps(keys: string[]) {
    this.renderPropKeys = new Set(keys);
  }

  setCssRefs(entries: string[]) {
    this.cssProps = new Set(entries);
  }

  applyCallbackDelta(delta: { add?: string[]; remove?: string[] }) {
    // Only update the internal callback path registry and cache. We rely on
    // accompanying update_props operations that contain the "$cb" placeholder
    // to trigger prop updates; transformValue will resolve to functions.
    if (delta.remove) {
      for (const key of delta.remove) {
        this.callbacks.delete(key);
        this.callbackCache.delete(key);
      }
    }
    if (delta.add) {
      for (const key of delta.add) {
        this.callbacks.add(key);
      }
    }
    this.callbackList = [...this.callbacks].sort();
  }

  applyRenderPropsDelta(delta: { add?: string[]; remove?: string[] }) {
    if (delta.remove) {
      for (const key of delta.remove) {
        this.renderPropKeys.delete(key);
      }
    }
    if (delta.add) {
      for (const key of delta.add) {
        this.renderPropKeys.add(key);
      }
    }
  }

  applyCssRefsDelta(delta: { set?: string[]; remove?: string[] }) {
    if (delta.set) {
      for (const prop of delta.set) {
        this.cssProps.add(prop);
      }
    }
    if (delta.remove) {
      for (const prop of delta.remove) {
        this.cssProps.delete(prop);
      }
    }
  }

  getCallback(path: string, prop: string) {
    const key = this.propPath(path, prop);
    let fn = this.callbackCache.get(key);
    if (!fn) {
      fn = (...args: any[]) => this.client.invokeCallback(this.path, key, args);
      this.callbackCache.set(key, fn);
    }
    return fn;
  }

  renderNode(node: VDOMNode, currentPath = ""): React.ReactNode {
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
        newProps[propName] = this.transformValue(
          currentPath,
          propName,
          propValue
        );
      }

      if (node.key) {
        newProps.key = node.key;
      }

      const renderedChildren = [];
      for (let index = 0; index < children.length; index += 1) {
        const child = children[index]!;
        const childPath = currentPath
          ? `${currentPath}.${index}`
          : String(index);
        renderedChildren.push(this.renderNode(child, childPath));
      }

      if (isMountPointNode(node)) {
        const componentKey = node.tag.slice(MOUNT_POINT_PREFIX.length);
        const Component = this.components[componentKey]!;
        if (!Component) {
          throw new Error(
            `Could not find component ${componentKey}. This is a Pulse internal error.`
          );
        }
        return createElement(Component, newProps, ...renderedChildren);
      }

      return createElement(
        tag === FRAGMENT_TAG ? React.Fragment : tag,
        newProps,
        ...renderedChildren
      );
    }

    // Fallback for unknown node types
    if (process.env.NODE_ENV !== "production") {
      console.error("Unknown VDOM node type:", node);
    }
    return null;
  }

  private propPath(path: string, prop: string) {
    return path ? `${path}.${prop}` : prop;
  }

  transformValue(path: string, key: string, value: any) {
    const propPath = this.propPath(path, key);
    if (this.callbacks.has(propPath)) {
      return this.getCallback(path, key);
    }
    if (this.renderPropKeys.has(propPath)) {
      return this.renderNode(value, propPath);
    }
    if (this.cssProps.has(propPath)) {
      return this.resolveCssToken(value);
    }
    return value;
  }

  private resolveCssToken(token: string): string {
    const idx = token.indexOf(":");
    if (idx === -1) {
      return token;
    }
    const moduleId = token.slice(0, idx);
    const className = token.slice(idx + 1);
    if (!moduleId || !className) {
      return token;
    }
    const mod = this.cssModules[moduleId];
    if (!mod) {
      throw new Error(
        `Received CSS reference for unknown module '${moduleId}'`
      );
    }
    const resolved = mod[className];
    if (typeof resolved !== "string") {
      throw new Error(
        `Received CSS reference for missing class '${className}' in module '${moduleId}'`
      );
    }
    return resolved;
  }
}

// =================================================================
// Update Functions (shallow-clone along update path)
// =================================================================

function ensureChildrenArray(el: React.ReactElement): React.ReactNode[] {
  const children = (el.props as any)?.children as React.ReactNode | undefined;
  if (children == null) return [];
  return Array.isArray(children) ? children.slice() : [children];
}

export function applyUpdates(
  initialTree: React.ReactNode,
  updates: VDOMUpdate[],
  renderer: VDOMRenderer
): React.ReactNode {
  let newTree: React.ReactNode = initialTree;
  for (const update of updates) {
    if (update.type === "update_callbacks") {
      renderer.applyCallbackDelta(update.data);
      continue;
    }
    if (update.type === "update_css_refs") {
      renderer.applyCssRefsDelta(update.data);
      continue;
    }
    if (update.type === "update_render_props") {
      renderer.applyRenderPropsDelta(update.data);
      continue;
    }

    const parts = update.path.split(".").filter((s) => s.length > 0);

    const descend = (
      node: React.ReactNode,
      depth: number,
      currentPath: string
    ): React.ReactNode => {
      if (depth < parts.length) {
        assertIsElement(node, parts, depth);
        const element = node as React.ReactElement<Record<string, any> | null>;
        const childKey = parts[depth]!;
        const childIdx = +childKey;
        const childPath = currentPath ? `${currentPath}.${childKey}` : childKey;
        if (!Number.isNaN(childIdx)) {
          // Regular child traversal
          const childrenArr = ensureChildrenArray(element);
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
          return renderer.renderNode(update.data, update.path);
        }
        case "update_props": {
          assertIsElement(node, parts, depth);
          const element = node as React.ReactElement;
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
              nextProps[k] = renderer.transformValue(currentPath, k, v);
            }
          }
          // Not passing children -> only update the props
          return cloneElement(element, nextProps);
        }
        case "insert": {
          assertIsElement(node, parts, depth);
          const element = node as React.ReactElement;
          const children = ensureChildrenArray(element);
          const childPath = currentPath
            ? `${currentPath}.${update.idx}`
            : String(update.idx);
          children.splice(
            update.idx,
            0,
            renderer.renderNode(update.data, childPath)
          );
          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(element, null!, ...children);
        }
        case "remove": {
          assertIsElement(node, parts, depth);
          const element = node as React.ReactElement;
          const children = ensureChildrenArray(element);
          children.splice(update.idx, 1);
          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(element, null!, ...children);
        }
        case "move": {
          assertIsElement(node, parts, depth);
          const element = node as React.ReactElement;
          const children = ensureChildrenArray(element);
          const item = children.splice(update.data.from_index, 1)[0];
          children.splice(update.data.to_index, 0, item);

          // Rebind callbacks for affected index range (indices whose path changed)
          const start = Math.min(update.data.from_index, update.data.to_index);
          const end = Math.max(update.data.from_index, update.data.to_index);
          for (let i = start; i <= end; i++) {
            const childPath = currentPath ? `${currentPath}.${i}` : String(i);
            if (renderer.hasAnyCallbackUnder(childPath)) {
              children[i] = rebindCallbacksInSubtree(
                children[i],
                childPath,
                renderer
              ) as any;
            }
          }

          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(element, null!, ...children);
        }
        default:
          throw new Error(
            `[Pulse renderer] Unknown update type: ${update["type"]}`
          );
      }
    };

    newTree = descend(newTree, 0, "");
  }
  return newTree;
}

// The `component` prop should be something like `() =>
// import('~/path/to/component') (we'll need to remap if we're importing a named export and not the default)
export function RenderLazy(
  component: () => Promise<{ default: ComponentType<any> }>,
  fallback?: React.ReactNode
): React.FC<React.PropsWithChildren<unknown>> {
  const Component = lazy(component);
  return ({ children, ...props }: React.PropsWithChildren<unknown>) => {
    return (
      <Suspense fallback={fallback ?? <></>}>
        <Component {...props}>{children}</Component>
      </Suspense>
    );
  };
}

function assertIsElement(
  node: React.ReactNode,
  parts: string[],
  depth: number
): node is React.ReactElement {
  if (process.env.NODE_ENV !== "production" && !isValidElement(node)) {
    console.error("Invalid node:", node);
    throw new Error("Invalid node at path " + parts.slice(0, depth).join("."));
  }
  return true;
}

// Rebind callback function props within a subtree after a path-changing move
function rebindCallbacksInSubtree(
  node: React.ReactNode,
  path: string,
  renderer: VDOMRenderer
): React.ReactNode {
  if (!isValidElement(node)) return node;
  const element = node as React.ReactElement<Record<string, any> | null>;
  const baseProps = (element.props ?? {}) as Record<string, any>;
  const nextProps: Record<string, any> = { ...baseProps };

  // Rebind only callback props; CSS refs are path-agnostic and render-props
  // are handled by the server-side renderer via explicit updates
  for (const key of Object.keys(baseProps)) {
    const propPath = path ? `${path}.${key}` : key;
    if (renderer.hasCallbackPath(propPath)) {
      nextProps[key] = renderer.getCallback(path, key);
    }
  }

  const children = ensureChildrenArray(element).map((child, idx) => {
    const childPath = path ? `${path}.${idx}` : String(idx);
    if (renderer.hasAnyCallbackUnder(childPath)) {
      return rebindCallbacksInSubtree(child, childPath, renderer);
    } else {
      return child;
    }
  });

  return cloneElement(element, nextProps, ...children);
}

// Binary-search lower bound for prefix matching on sorted callback paths
function lowerBound(arr: string[], target: string): number {
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
