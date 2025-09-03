import React, { Suspense, type ComponentType } from "react";
import type {
  ComponentRegistry,
  RegistryEntry,
  VDOMElement,
  VDOMNode,
  VDOMUpdate,
} from "./vdom";
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
        return React.createElement(
          Component,
          processedProps,
          ...renderedChildren
        );
      }

      return React.createElement(
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
  return React.cloneElement(el, undefined, ...children);
}

export function applyReactTreeUpdates(
  initialTree: React.ReactNode,
  updates: VDOMUpdate[],
  renderer: VDOMRenderer
): React.ReactNode {
  let newTree: React.ReactNode = initialTree;

  const updateParentAtPath = (
    node: React.ReactNode,
    pathParts: number[],
    onParent: (parentEl: React.ReactElement) => React.ReactElement
  ): React.ReactNode => {
    if (pathParts.length === 0) {
      if (!React.isValidElement(node)) return node;
      return onParent(node);
    }
    if (!React.isValidElement(node)) return node;
    const idx = pathParts[0]!;
    const rest = pathParts.slice(1);
    const childrenArr = toChildrenArrayFromElement(node);
    const child = childrenArr[idx];
    childrenArr[idx] = updateParentAtPath(child, rest, onParent) as any;
    return cloneElementWithChildren(node, childrenArr);
  };

  for (const update of updates) {
    const { type, path, data } = update;

    if (path === "") {
      switch (type) {
        case "replace": {
          newTree = renderer.renderNode(data);
          break;
        }
        case "update_props": {
          if (React.isValidElement(newTree)) {
            const nextProps = processPropsForCallbacks(renderer, data);
            const currentChildren = toChildrenArrayFromElement(newTree);
            newTree = React.cloneElement(
              newTree,
              nextProps,
              ...currentChildren
            );
          }
          break;
        }
        default: {
          if (process.env.NODE_ENV !== "production") {
            console.error(
              `[applyReactTreeUpdates] Invalid root operation: ${type}`
            );
          }
        }
      }
      continue;
    }

    const parts = path.split(".").map(Number);
    const parentParts = parts.slice(0, -1);
    const childIndex = parts[parts.length - 1]!;

    switch (type) {
      case "replace": {
        newTree = updateParentAtPath(newTree, parentParts, (parentEl) => {
          const childrenArr = toChildrenArrayFromElement(parentEl);
          childrenArr[childIndex] = renderer.renderNode(data);
          return cloneElementWithChildren(parentEl, childrenArr);
        });
        break;
      }
      case "update_props": {
        newTree = updateParentAtPath(newTree, parentParts, (parentEl) => {
          const childrenArr = toChildrenArrayFromElement(parentEl);
          const target = childrenArr[childIndex];
          if (React.isValidElement(target)) {
            const nextProps = processPropsForCallbacks(renderer, data);
            const currentChildren = toChildrenArrayFromElement(target);
            childrenArr[childIndex] = React.cloneElement(
              target,
              nextProps,
              ...currentChildren
            );
          }
          return cloneElementWithChildren(parentEl, childrenArr);
        });
        break;
      }
      case "insert": {
        newTree = updateParentAtPath(newTree, parentParts, (parentEl) => {
          const childrenArr = toChildrenArrayFromElement(parentEl);
          childrenArr.splice(childIndex, 0, renderer.renderNode(data));
          return cloneElementWithChildren(parentEl, childrenArr);
        });
        break;
      }
      case "remove": {
        newTree = updateParentAtPath(newTree, parentParts, (parentEl) => {
          const childrenArr = toChildrenArrayFromElement(parentEl);
          childrenArr.splice(childIndex, 1);
          return cloneElementWithChildren(parentEl, childrenArr);
        });
        break;
      }
      case "move": {
        newTree = updateParentAtPath(newTree, parentParts, (parentEl) => {
          const childrenArr = toChildrenArrayFromElement(parentEl);
          const item = childrenArr.splice(data.from_index, 1)[0];
          childrenArr.splice(data.to_index, 0, item);
          return cloneElementWithChildren(parentEl, childrenArr);
        });
        break;
      }
      default: {
        if (process.env.NODE_ENV !== "production") {
          console.error(`[applyReactTreeUpdates] Unknown update type: ${type}`);
        }
      }
    }
  }

  return newTree;
}

// The `component` prop should be something like `() =>
// import('~/path/to/component') (we'll need to remap if we're importing a named export and not the default)
export function RenderLazy(
  component: () => Promise<{ default: ComponentType<any> }>,
  fallback?: React.ReactNode
): React.FC<React.PropsWithChildren<unknown>> {
  const Component = React.lazy(component);
  return ({ children, ...props }: React.PropsWithChildren<unknown>) => {
    return (
      <Suspense fallback={fallback ?? <></>}>
        <Component {...props}>{children}</Component>
      </Suspense>
    );
  };
}
