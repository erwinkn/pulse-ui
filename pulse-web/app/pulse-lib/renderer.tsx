import React, { memo } from "react";
import type { VDOM, VDOMElement, VDOMNode, VDOMUpdate } from "./vdom";
import {
  isElementNode,
  isFragment,
  isMountPointNode,
  getMountPointComponentKey,
  MOUNT_POINT_PREFIX,
  FRAGMENT_TAG,
} from "./vdom";
import { usePulseRenderHelpers } from "./pulse";

interface VDOMRendererProps {
  node: VDOMNode;
}

// Helper function to generate keys for React reconciliation
function getNodeKey(node: VDOMNode, index: number): string | number {
  if (isElementNode(node)) {
    return node.key || index;
  }
  return index;
}

export const VDOMRenderer = memo<VDOMRendererProps>(({ node }) => {
  const { getCallback, getComponent } = usePulseRenderHelpers();

  // 1. Handle non-renderable cases first
  if (node === null || typeof node === "boolean" || node === undefined) {
    return null;
  }

  // 2. Handle primitive nodes
  if (typeof node === "string" || typeof node === "number") {
    return <>{node}</>;
  }

  // 3. Handle element nodes
  if (isElementNode(node)) {
    if (process.env.NODE_ENV !== "production") {
      const hasTag = "tag" in node && typeof node.tag === "string";
      if (!hasTag) {
        console.error("Invalid VDOM element node received:", node);
        return null;
      }
    }

    const { tag, props = {}, children = [] } = node;

    // Process props for callbacks
    const processedProps: Record<string, any> = {};
    for (const [key, value] of Object.entries(props)) {
      if (typeof value === "string" && value.startsWith("$$callback:")) {
        const callbackKey = value.substring("$$callback:".length);
        processedProps[key] = getCallback(callbackKey);
      } else {
        processedProps[key] = value;
      }
    }

    if (isMountPointNode(node)) {
      const componentKey = getMountPointComponentKey(node);
      const Component = getComponent(componentKey);
      const renderedChildren = children.map((child, index) => (
        <VDOMRenderer key={getNodeKey(child, index)} node={child} />
      ));
      return <Component {...processedProps}>{renderedChildren}</Component>;
    }

    if (tag === FRAGMENT_TAG) {
      return (
        <>
          {children.map((child, index) => (
            <VDOMRenderer key={getNodeKey(child, index)} node={child} />
          ))}
        </>
      );
    }

    const renderedChildren = children.map((child, index) => (
      <VDOMRenderer key={getNodeKey(child, index)} node={child} />
    ));

    return React.createElement(tag, processedProps, ...renderedChildren);
  }

  // 4. Fallback for unknown node types
  if (process.env.NODE_ENV !== "production") {
    console.error("Unknown VDOM node type:", node);
  }
  return null;
});

VDOMRenderer.displayName = "VDOMRenderer";

// =================================================================
// Node Creation Functions
// =================================================================

export function createElementNode(
  tag: string,
  props: Record<string, any> = {},
  children: VDOMNode[] = [],
  key?: string
): VDOMElement {
  if (process.env.NODE_ENV !== "production") {
    if (tag.startsWith(MOUNT_POINT_PREFIX)) {
      console.error(
        `[Pulse] Error: The tag "${tag}" starts with a reserved prefix "${MOUNT_POINT_PREFIX}". Please use a different tag name.`
      );
    }
  }

  const node: VDOMElement = {
    tag,
    props,
    children,
  };

  if (key !== undefined) {
    node.key = key;
  }

  return node;
}

export function createFragment(
  children: VDOMNode[] = [],
  key?: string
): VDOMElement {
  const node: VDOMElement = {
    tag: FRAGMENT_TAG,
    props: {},
    children,
  };

  if (key !== undefined) {
    node.key = key;
  }

  return node;
}

export function createMountPoint(
  componentKey: string,
  props: Record<string, any> = {},
  children: VDOMNode[] = [],
  key?: string
): VDOMElement {
  const node: VDOMElement = {
    tag: MOUNT_POINT_PREFIX + componentKey,
    props,
    children,
  };

  if (key !== undefined) {
    node.key = key;
  }

  return node;
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
    current = current.children[index];
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

export function applyVDOMUpdates(
  initialTree: VDOMNode,
  updates: VDOMUpdate[]
): VDOMNode {
  let newTree = cloneNode(initialTree);

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
        const nodeToUpdate = targetParent.children[childIndex];
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
        const item = targetParent.children.splice(data.from_index, 1)[0];
        targetParent.children.splice(data.to_index, 0, item);
        break;
      }
    }
  }

  return newTree;
}
