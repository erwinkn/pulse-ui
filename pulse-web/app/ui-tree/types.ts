// Special string to identify fragment nodes
export const FRAGMENT_TAG = '$$fragment';

export interface UIElementNode {
  id: string;
  tag: string;
  props: Record<string, any>;
  children: UINode[];
  key?: string;
}

export interface UIMountPointNode {
  id: string;
  componentKey: string;
  props: Record<string, any>;
  key?: string;
}

// UINode is either a string (for text), an element/fragment node, or a mount point
export type UINode = string | UIElementNode | UIMountPointNode;

export type UITree = UINode;

export type UpdateType = 'insert' | 'remove' | 'replace' | 'update_props';

export interface UIUpdate {
  id: string;
  type: UpdateType;
  path: number[];
  data?: any;
}

export interface InsertUpdate extends UIUpdate {
  type: 'insert';
  data: {
    node: UINode;
    index: number;
  };
}

export interface RemoveUpdate extends UIUpdate {
  type: 'remove';
  data: {
    index: number;
  };
}

export interface ReplaceUpdate extends UIUpdate {
  type: 'replace';
  data: {
    node: UINode;
  };
}


export interface UpdatePropsUpdate extends UIUpdate {
  type: 'update_props';
  data: {
    props: Record<string, any>;
  };
}

export type UIUpdatePayload = InsertUpdate | RemoveUpdate | ReplaceUpdate | UpdatePropsUpdate;

// Utility functions for working with the UI tree structure
export function isElementNode(node: UINode): node is UIElementNode {
  return typeof node === 'object' && node !== null && 'tag' in node;
}

export function isMountPointNode(node: UINode): node is UIMountPointNode {
  return typeof node === 'object' && node !== null && 'componentKey' in node;
}

export function isTextNode(node: UINode): node is string {
  return typeof node === 'string';
}

export function isFragment(node: UINode): boolean {
  return isElementNode(node) && node.tag === FRAGMENT_TAG;
}

export function createElementNode(
  tag: string, 
  props: Record<string, any> = {}, 
  children: UINode[] = []
): UIElementNode {
  // Validate that user isn't trying to use the special fragment tag
  if (tag === FRAGMENT_TAG) {
    throw new Error(`The tag '${FRAGMENT_TAG}' is reserved for internal fragment nodes. Please use a different tag name.`);
  }
  
  return {
    id: Math.random().toString(36),
    tag,
    props,
    children,
  };
}

export function createFragment(children: UINode[] = []): UIElementNode {
  return {
    id: Math.random().toString(36),
    tag: FRAGMENT_TAG,
    props: {},
    children,
  };
}

export function createMountPoint(
  componentKey: string,
  props: Record<string, any> = {}
): UIMountPointNode {
  return {
    id: Math.random().toString(36),
    componentKey,
    props,
  };
}