// Special prefixes for reserved node types
export const FRAGMENT_TAG = "$$fragment";
export const MOUNT_POINT_PREFIX = "$$";

export interface UIElementNode {
  tag: string;
  props: Record<string, any>;
  children: UINode[];
  key?: string;
}

// UINode is either a string (for text) or an element node
// Mount points are just UIElementNodes with tags starting with $$ComponentKey
export type UINode = string | UIElementNode;

export type UITree = UINode;

export type UpdateType = "insert" | "remove" | "replace" | "update_props";

export interface UIUpdate {
  type: UpdateType;
  path: number[];
  data?: any;
}

export interface InsertUpdate extends UIUpdate {
  type: "insert";
  data: {
    node: UINode;
    index: number;
  };
}

export interface RemoveUpdate extends UIUpdate {
  type: "remove";
  data: {
    index: number;
  };
}

export interface ReplaceUpdate extends UIUpdate {
  type: "replace";
  data: {
    node: UINode;
  };
}

export interface UpdatePropsUpdate extends UIUpdate {
  type: "update_props";
  data: {
    props: Record<string, any>;
  };
}

export type UIUpdatePayload =
  | InsertUpdate
  | RemoveUpdate
  | ReplaceUpdate
  | UpdatePropsUpdate;

// Utility functions for working with the UI tree structure
export function isElementNode(node: UINode): node is UIElementNode {
  // Matches all non-text nodes
  return typeof node === "object";
}

export function isMountPointNode(node: UINode): node is UIElementNode {
  return (
    typeof node === "object" &&
    node.tag.startsWith(MOUNT_POINT_PREFIX) &&
    node.tag !== FRAGMENT_TAG
  );
}

export function isTextNode(node: UINode): node is string {
  return typeof node === "string";
}

export function isFragment(node: UINode): boolean {
  return typeof node === "object" && node.tag === FRAGMENT_TAG;
}

export function getMountPointComponentKey(node: UIElementNode): string {
  if (!isMountPointNode(node)) {
    throw new Error("Node is not a mount point");
  }
  return node.tag.slice(MOUNT_POINT_PREFIX.length);
}

export function createElementNode(
  tag: string,
  props: Record<string, any> = {},
  children: UINode[] = [],
  key?: string
): UIElementNode {
  // Validate that user isn't trying to use reserved prefixes
  if (tag.startsWith(MOUNT_POINT_PREFIX)) {
    throw new Error(
      `Tags starting with '${MOUNT_POINT_PREFIX}' are reserved for internal use. Please use a different tag name.`
    );
  }

  const node: UIElementNode = {
    tag,
    props,
    children,
  };
  
  if (key !== undefined) {
    node.key = key;
  }
  
  return node;
}

export function createFragment(children: UINode[] = [], key?: string): UIElementNode {
  const node: UIElementNode = {
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
  children: UINode[] = [],
  key?: string
): UIElementNode {
  const node: UIElementNode = {
    tag: MOUNT_POINT_PREFIX + componentKey,
    props,
    children,
  };
  
  if (key !== undefined) {
    node.key = key;
  }
  
  return node;
}
