import React, { cloneElement, createElement, isValidElement, lazy, Suspense, type ComponentType } from "react";
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
  constructor(
    private client: PulseSocketIOClient,
    private path: string,
    private components: ComponentRegistry
  ) {
    this.callbackCache = new Map();
  }

  getCallback(key: string) {
    let fn = this.callbackCache.get(key);
    if (!fn) {
      fn = (...args) => this.client.invokeCallback(this.path, key, args);
      this.callbackCache.set(key, fn);
    }
    return fn;
  }

  renderNode(node: VDOMNode): React.ReactNode {
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

      // Process props for callbacks
      const processedProps: Record<string, any> = {};
      for (const [propKey, value] of Object.entries(props)) {
        if (typeof value === "string" && value.startsWith("$$fn:")) {
          const callbackKey = value.substring("$$fn:".length);
          processedProps[propKey] = this.getCallback(callbackKey);
        } else {
          processedProps[propKey] = value;
        }
      }
      if (node.key) {
        processedProps.key = node.key;
      }

      const renderedChildren = [];
      for (const child of children) {
        renderedChildren.push(this.renderNode(child));
      }

      if (isMountPointNode(node)) {
        const componentKey = node.tag.slice(MOUNT_POINT_PREFIX.length);
        const Component = this.components[componentKey]!;
        return createElement(
          Component,
          processedProps,
          ...renderedChildren
        );
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
}

// =================================================================
// Update Functions (shallow-clone along update path)
// =================================================================

function toChildrenArrayFromElement(el: React.ReactElement): React.ReactNode[] {
  const children = (el.props as any)?.children as React.ReactNode | undefined;
  if (children == null) return [];
  return Array.isArray(children) ? children.slice() : [children];
}

function processPropsForCallbacks(
  renderer: VDOMRenderer,
  props: Record<string, any>
): Record<string, any> {
  const processed: Record<string, any> = {};
  for (const [propKey, value] of Object.entries(props || {})) {
    if (typeof value === "string" && value.startsWith("$$fn:")) {
      const callbackKey = value.substring("$$fn:".length);
      processed[propKey] = renderer.getCallback(callbackKey);
    } else {
      processed[propKey] = value;
    }
  }
  return processed;
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
    const parts = update.path
      .split(".")
      .filter((s) => s.length > 0)
      .map(Number);

    const descend = (node: React.ReactNode, depth: number): React.ReactNode => {
      if (depth < parts.length) {
        assertIsElement(node, parts, depth);
        node = node as React.ReactElement;
        const childIdx = parts[depth]!;
        const childrenArr = toChildrenArrayFromElement(node);
        const child = childrenArr[childIdx];
        childrenArr[childIdx] = descend(child, depth + 1) as any;
        return cloneElementWithChildren(node, childrenArr);
      }
      switch (update.type) {
        case "replace": {
          return renderer.renderNode(update.data);
        }
        case "update_props": {
          assertIsElement(node, parts, depth);
          node = node as React.ReactElement;
          const nextProps = processPropsForCallbacks(renderer, update.data);
          // Not passing children -> only update the props
          return cloneElement(node, nextProps);
        }
        case "insert": {
          assertIsElement(node, parts, depth);
          node = node as React.ReactElement;
          const children = toChildrenArrayFromElement(node);
          children.splice(update.idx, 0, renderer.renderNode(update.data));
          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(node, null!, ...children);
        }
        case "remove": {
          assertIsElement(node, parts, depth);
          node = node as React.ReactElement;
          const children = toChildrenArrayFromElement(node);
          children.splice(update.idx, 1);
          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(node, null!, ...children);
        }
        case "move": {
          assertIsElement(node, parts, depth);
          node = node as React.ReactElement;
          const children = toChildrenArrayFromElement(node);
          const item = children.splice(update.data.from_index, 1)[0];
          children.splice(update.data.to_index, 0, item);
          // Only update the children (TypeScript doesn't like the `null`, but that's what the official React docs say)
          return cloneElement(node, null!, ...children);
        }
        default:
          throw new Error(
            `[Pulse renderer] Unknown update type: ${update["type"]}`
          );
      }
    };

    newTree = descend(newTree, 0);
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
