import type { ComponentType } from "react";

// Special prefixes for reserved node types
export const FRAGMENT_TAG = "$$fragment";
export const MOUNT_POINT_PREFIX = "$$";

export interface VDOMElement {
  tag: string;
  props?: Record<string, any>;
  children?: VDOMNode[];
  key?: string;
}

// Primitive nodes that can be rendered
export type PrimitiveNode = string | number | boolean;

// VDOMNode is either a primitive (string, number, boolean) or an element node.
// Booleans are valid children in React but do not render anything.
// Mount points are just UIElementNodes with tags starting with $$ComponentKey
export type VDOMNode = PrimitiveNode | VDOMElement;

export type VDOM = VDOMNode;

export type UpdateType =
  | "insert"
  | "remove"
  | "replace"
  | "update_props"
  | "move";

export interface VDOMUpdateBase {
  type: UpdateType;
  path: string; // Dot-separated path to the node
  data?: any;
}

export interface InsertUpdate extends VDOMUpdateBase {
  type: "insert";
  data: VDOMNode; // The node to insert
}

export interface RemoveUpdate extends VDOMUpdateBase {
  type: "remove";
  data?: string; // Optional key for keyed removals
}

export interface ReplaceUpdate extends VDOMUpdateBase {
  type: "replace";
  data: VDOMNode; // The new node
}

export interface UpdatePropsUpdate extends VDOMUpdateBase {
  type: "update_props";
  data: Record<string, any>; // The new props
}

export interface MoveUpdate extends VDOMUpdateBase {
  type: "move";
  data: {
    from_index: number;
    to_index: number;
    key: string;
  };
}

export type VDOMUpdate =
  | InsertUpdate
  | RemoveUpdate
  | ReplaceUpdate
  | UpdatePropsUpdate
  | MoveUpdate;

// Utility functions for working with the UI tree structure
export function isElementNode(node: VDOMNode): node is VDOMElement {
  // Matches all non-text nodes
  return typeof node === "object" && node !== null;
}

export function isMountPointNode(node: VDOMNode): node is VDOMElement {
  return (
    typeof node === "object" &&
    node !== null &&
    node.tag.startsWith(MOUNT_POINT_PREFIX) &&
    node.tag !== FRAGMENT_TAG
  );
}

export function isTextNode(node: VDOMNode): node is string {
  return typeof node === "string";
}

export function isFragment(node: VDOMNode): boolean {
  return typeof node === "object" && node !== null && node.tag === FRAGMENT_TAG;
}

export function getMountPointComponentKey(node: VDOMElement): string {
  if (!isMountPointNode(node)) {
    throw new Error("Node is not a mount point");
  }
  return node.tag.slice(MOUNT_POINT_PREFIX.length);
}
