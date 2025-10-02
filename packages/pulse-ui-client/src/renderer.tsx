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
  private callbackCache: Map<string, (...args: any[]) => void>;
  private callbackProps: Map<string, Set<string>>;
  private renderPropKeys: Set<string>;
  constructor(
    private client: PulseSocketIOClient,
    private path: string,
    private components: ComponentRegistry,
    initialCallbacks: string[] = [],
    initialRenderProps: string[] = []
  ) {
    this.callbackCache = new Map();
    this.callbackProps = new Map();
    this.renderPropKeys = new Set(initialRenderProps);
    this.setCallbacks(initialCallbacks);
  }

  setCallbacks(keys: string[]) {
    this.callbackProps.clear();
    this.callbackCache.clear();
    for (const key of keys) {
      const [path, prop] = this.splitPropPath(key);
      if (!this.callbackProps.has(path)) {
        this.callbackProps.set(path, new Set());
      }
      this.callbackProps.get(path)!.add(prop);
    }
  }

  applyCallbackDelta(
    delta: { add?: string[]; remove?: string[] },
    tree: React.ReactNode
  ): React.ReactNode {
    const beforeMap = new Map<string, Set<string>>();
    const recordBefore = (path: string) => {
      if (!beforeMap.has(path)) {
        beforeMap.set(path, new Set(this.callbackProps.get(path) ?? []));
      }
    };

    if (delta.remove) {
      for (const key of delta.remove) {
        const [path, prop] = this.splitPropPath(key);
        recordBefore(path);
        const current = this.callbackProps.get(path);
        if (!current) {
          this.callbackCache.delete(key);
          continue;
        }
        this.callbackCache.delete(key);
        current.delete(prop);
        if (current.size === 0) {
          this.callbackProps.delete(path);
        }
      }
    }

    if (delta.add) {
      for (const key of delta.add) {
        const [path, prop] = this.splitPropPath(key);
        recordBefore(path);
        if (!this.callbackProps.has(path)) {
          this.callbackProps.set(path, new Set());
        }
        this.callbackProps.get(path)!.add(prop);
      }
    }

    let nextTree = tree;
    for (const [path, before] of beforeMap.entries()) {
      const after = new Set(this.callbackProps.get(path) ?? []);
      if (this.setsEqual(before, after)) {
        continue;
      }
      const parts = path
        ? path.split(".").filter((segment) => segment.length > 0)
        : [];
      nextTree = this.updateCallbacksOnTree(
        nextTree,
        parts,
        0,
        path,
        before,
        after
      );
    }

    return nextTree;
  }

  setRenderProps(keys: string[]) {
    this.renderPropKeys = new Set(keys);
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

      const processedProps: Record<string, any> = { ...(props || {}) };

      // Apply callbacks
      for (const propName of this.getCallbackNames(currentPath)) {
        processedProps[propName] = this.getCallback(currentPath, propName);
      }

      // Detect and render any render props (VDOM objects in props)
      for (const [propName, propValue] of Object.entries(processedProps)) {
        const renderPropKey = this.propPath(currentPath, propName);
        if (this.renderPropKeys.has(renderPropKey)) {
          // This prop is a render prop - render the VDOM to React
          const renderPropPath = currentPath
            ? `${currentPath}.${propName}`
            : propName;
          processedProps[propName] = this.renderNode(propValue, renderPropPath);
        }
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
        if(!Component) {
          throw new Error(`Could not find component ${componentKey}. This is a Pulse internal error.`)
        }
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

  private splitPropPath(key: string): [path: string, prop: string] {
    const lastDot = key.lastIndexOf(".");
    if (lastDot === -1) {
      return ["", key];
    }
    return [key.slice(0, lastDot), key.slice(lastDot + 1)];
  }

  private propPath(path: string, prop: string) {
    return path ? `${path}.${prop}` : prop;
  }

  private getCallbackNames(path: string): string[] {
    const props = this.callbackProps.get(path);
    return props ? Array.from(props) : [];
  }

  transformValue(path: string, key: string, value: any) {
    const callbacks = this.callbackProps.get(path);
    const propPath = this.propPath(path, key);
    if (callbacks && callbacks.size > 0 && callbacks.has(key)) {
      return this.getCallback(path, key);
    }
    if (this.renderPropKeys.has(propPath)) {
      return this.renderNode(value, propPath);
    }
    return value;
  }

  private updateCallbacksOnTree(
    node: React.ReactNode,
    parts: string[],
    depth: number,
    currentPath: string,
    before: Set<string>,
    after: Set<string>
  ): React.ReactNode {
    if (depth < parts.length) {
      assertIsElement(node, parts, depth);
      const element = node as React.ReactElement<Record<string, any> | null>;
      const segment = parts[depth]!;
      const childIdx = Number(segment);
      const nextPath = currentPath ? `${currentPath}.${segment}` : segment;
      if (!Number.isNaN(childIdx)) {
        const childrenArr = ensureChildrenArray(element);
        const child = childrenArr[childIdx];
        const updatedChild = this.updateCallbacksOnTree(
          child,
          parts,
          depth + 1,
          nextPath,
          before,
          after
        );
        if (updatedChild === child) {
          return node;
        }
        childrenArr[childIdx] = updatedChild as any;
        return cloneElement(element, undefined, ...childrenArr);
      } else {
        const baseProps = (element.props ?? {}) as Record<string, any>;
        const child = baseProps[segment];
        const updatedChild = this.updateCallbacksOnTree(
          child,
          parts,
          depth + 1,
          nextPath,
          before,
          after
        );
        if (updatedChild === child) {
          return node;
        }
        return cloneElement(element, {
          ...baseProps,
          [segment]: updatedChild,
        });
      }
    }

    if (!isValidElement(node)) {
      return node;
    }

    const element = node as React.ReactElement<Record<string, any> | null>;
    const currentProps = (element.props ?? {}) as Record<string, any>;
    let changed = false;
    const nextProps: Record<string, any> = { ...currentProps };

    for (const prop of before) {
      if (!after.has(prop) && prop in nextProps) {
        delete nextProps[prop];
        changed = true;
      }
    }

    for (const prop of after) {
      const fn = this.getCallback(currentPath, prop);
      if (nextProps[prop] !== fn) {
        nextProps[prop] = fn;
        changed = true;
      }
    }

    if (!changed) {
      return node;
    }
    return cloneElement(element, nextProps);
  }

  private setsEqual(left: Set<string>, right: Set<string>): boolean {
    if (left.size !== right.size) {
      return false;
    }
    for (const value of left) {
      if (!right.has(value)) {
        return false;
      }
    }
    return true;
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
      newTree = renderer.applyCallbackDelta(update.data, newTree);
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
              if (key in nextProps) delete nextProps[key];
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
