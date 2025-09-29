import React, {
  cloneElement,
  createElement,
  isValidElement,
  lazy,
  Suspense,
  type ComponentType,
} from "react";
import type { ComponentRegistry, VDOMNode, VDOMUpdate } from "./vdom";
import {
  FRAGMENT_TAG,
  isElementNode,
  isMountPointNode,
  MOUNT_POINT_PREFIX,
} from "./vdom";
import type { PulseSocketIOClient } from "./client";

export class VDOMRenderer {
  private callbackCache: Map<string, (...args: any[]) => void>;
  private callbackProps: Map<string, Set<string>>;
  constructor(
    private client: PulseSocketIOClient,
    private path: string,
    private components: ComponentRegistry,
    initialCallbacks: string[] = []
  ) {
    this.callbackCache = new Map();
    this.callbackProps = new Map();
    this.setCallbacks(initialCallbacks);
  }

  setCallbacks(keys: string[]) {
    this.callbackProps.clear();
    this.callbackCache.clear();
    for (const key of keys) {
      const { path, prop } = this.parseCallbackKey(key);
      if (!this.callbackProps.has(path)) {
        this.callbackProps.set(path, new Set());
      }
      this.callbackProps.get(path)!.add(prop);
    }
  }

  applyCallbackDelta(delta: { add?: string[]; remove?: string[] }) {
    if (delta.remove) {
      for (const key of delta.remove) {
        const { path, prop } = this.parseCallbackKey(key);
        const current = this.callbackProps.get(path);
        if (!current) continue;
        this.callbackCache.delete(key);
        current.delete(prop);
        if (current.size === 0) {
          this.callbackProps.delete(path);
        }
      }
    }
    if (delta.add) {
      for (const key of delta.add) {
        const { path, prop } = this.parseCallbackKey(key);
        if (!this.callbackProps.has(path)) {
          this.callbackProps.set(path, new Set());
        }
        this.callbackProps.get(path)!.add(prop);
      }
    }
  }

  getCallback(path: string, prop: string) {
    const key = this.makeCallbackKey(path, prop);
    let fn = this.callbackCache.get(key);
    if (!fn) {
      fn = (...args: any[]) => this.client.invokeCallback(this.path, key, args);
      this.callbackCache.set(key, fn);
    }
    return fn;
  }

  peekCallback(path: string, prop: string) {
    const key = this.makeCallbackKey(path, prop);
    return this.callbackCache.get(key);
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

      const processedProps: Record<string, any> = { ...(props || {}) };
      for (const propName of this.getCallbackNames(currentPath)) {
        processedProps[propName] = this.getCallback(currentPath, propName);
      }
      if (node.key) {
        processedProps.key = node.key;
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
        return createElement(Component, processedProps, ...renderedChildren);
      }

      return createElement(
        tag === FRAGMENT_TAG ? React.Fragment : tag,
        processedProps,
        ...renderedChildren
      );
    }

    // Fallback for unknown node types
    if (process.env.NODE_ENV !== "production") {
      console.error("Unknown VDOM node type:", node);
    }
    return null;
  }

  private makeCallbackKey(path: string, prop: string) {
    return path ? `${path}.${prop}` : prop;
  }

  private getCallbackNames(path: string): string[] {
    const props = this.callbackProps.get(path);
    return props ? Array.from(props) : [];
  }

  syncCallbackProps(path: string, props: Record<string, any>) {
    const callbacks = this.callbackProps.get(path);
    if (callbacks) {
      for (const name of callbacks) {
        props[name] = this.getCallback(path, name);
      }
    }
  }

  parseCallbackKey(key: string): { path: string; prop: string } {
    const lastDot = key.lastIndexOf(".");
    if (lastDot === -1) {
      return { path: "", prop: key };
    }
    return {
      path: key.slice(0, lastDot),
      prop: key.slice(lastDot + 1),
    };
  }
}

// =================================================================
// Update Functions (shallow-clone along update path)
// =================================================================

function toChildrenArrayFromElement(el: React.ReactElement): React.ReactNode[] {
  const children = (el.props as any)?.children as React.ReactNode | undefined;
  if (children == null) return [];
  return Array.isArray(children) ? children.slice() : [children];
}

function cloneElementWithChildren(
  el: React.ReactElement,
  children: React.ReactNode[]
): React.ReactElement {
  // Preserve existing props; only override children
  return cloneElement(el, undefined, ...children);
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

    const parts = update.path
      .split(".")
      .filter((s) => s.length > 0)
      .map(Number);

    const descend = (
      node: React.ReactNode,
      depth: number,
      currentPath: string
    ): React.ReactNode => {
      if (depth < parts.length) {
        assertIsElement(node, parts, depth);
        const element = node as React.ReactElement;
        const childIdx = parts[depth]!;
        const childrenArr = toChildrenArrayFromElement(element);
        const child = childrenArr[childIdx];
        const childPath = currentPath
          ? `${currentPath}.${childIdx}`
          : String(childIdx);
        childrenArr[childIdx] = descend(child, depth + 1, childPath) as any;
        return cloneElementWithChildren(element, childrenArr);
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
              if (key in nextProps) delete nextProps[key];
            }
          }
          if (delta.set) {
            for (const [k, v] of Object.entries(delta.set)) {
              nextProps[k] = v;
            }
          }
          renderer.syncCallbackProps(currentPath, nextProps);
          // Not passing children -> only update the props
          return cloneElement(element, nextProps);
        }
        case "insert": {
          assertIsElement(node, parts, depth);
          const element = node as React.ReactElement;
          const children = toChildrenArrayFromElement(element);
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
          const children = toChildrenArrayFromElement(element);
          children.splice(update.idx, 1);
          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(element, null!, ...children);
        }
        case "move": {
          assertIsElement(node, parts, depth);
          const element = node as React.ReactElement;
          const children = toChildrenArrayFromElement(element);
          const item = children.splice(update.data.from_index, 1)[0];
          children.splice(update.data.to_index, 0, item);
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
  parts: number[],
  depth: number
): node is React.ReactElement {
  if (process.env.NODE_ENV !== "production" && !isValidElement(node)) {
    console.error("Invalid node:", node);
    throw new Error("Invalid node at path " + parts.slice(0, depth).join("."));
  }
  return true;
}
