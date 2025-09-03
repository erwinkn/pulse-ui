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
// VDOM Update Functions
// =================================================================

function findNodeByPath(root: VDOMNode, path: string): VDOMElement | null {
  if (path === "") return isElementNode(root) ? root : null;

  const parts = path.split(".").map(Number);
  let current: VDOMNode | VDOMElement = root;

  for (const index of parts) {
    if (!isElementNode(current)) {
      console.error(
        `[findNodeByPath] Invalid path: part of it is not an element node.`
      );
      return null;
    }
    if (!current.children || index >= current.children.length) {
      console.error(
        `[findNodeByPath] Invalid path: index ${index} out of bounds.`
      );
      return null;
    }
    current = current.children[index]!;
  }

  return isElementNode(current) ? current : null;
}

function cloneNode<T extends VDOMNode>(node: T): T {
  if (typeof node !== "object" || node === null) {
    return node;
  }
  // Basic deep clone for VDOM nodes
  return JSON.parse(JSON.stringify(node));
}

// TODO: optimize by only cloning along the update path
export function applyVDOMUpdates(
  initialTree: VDOMNode,
  updates: VDOMUpdate[]
): VDOMNode {
  let newTree = structuredClone(initialTree);

  for (const update of updates) {
    const { type, path, data } = update;

    // Handle root-level operations separately
    if (path === "") {
      switch (type) {
        case "replace":
          newTree = data;
          break;
        case "update_props":
          if (isElementNode(newTree)) {
            newTree.props = { ...(newTree.props ?? {}), ...data };
          }
          break;
        default:
          console.error(`[applyUpdates] Invalid root operation: ${type}`);
      }
      continue; // Continue to next update
    }

    const parentPath = path.substring(0, path.lastIndexOf("."));
    const childIndex = parseInt(path.substring(path.lastIndexOf(".") + 1), 10);

    const targetParent = findNodeByPath(newTree, parentPath);

    if (!targetParent) {
      console.error(`[applyUpdates] Could not find parent for path: ${path}`);
      continue;
    }

    if (!targetParent.children) {
      targetParent.children = [];
    }

    switch (type) {
      case "replace":
        targetParent.children[childIndex] = data;
        break;

      case "update_props":
        const nodeToUpdate = targetParent.children[childIndex]!;
        if (isElementNode(nodeToUpdate)) {
          nodeToUpdate.props = { ...(nodeToUpdate.props ?? {}), ...data };
        }
        break;

      case "insert":
        targetParent.children.splice(childIndex, 0, data);
        break;

      case "remove":
        targetParent.children.splice(childIndex, 1);
        break;

      case "move": {
        const item = targetParent.children.splice(data.from_index, 1)[0]!;
        targetParent.children.splice(data.to_index, 0, item);
        break;
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
