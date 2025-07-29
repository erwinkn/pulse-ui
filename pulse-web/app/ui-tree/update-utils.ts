import type { UINode, UIElementNode, UIMountPointNode, UIUpdatePayload } from './types';
import { isElementNode, isTextNode, isMountPointNode } from './types';

function cloneUINode(node: UINode): UINode {
  if (isTextNode(node)) {
    return node; // strings are immutable, no need to clone
  }

  if (isElementNode(node)) {
    return {
      ...node,
      props: { ...node.props },
      children: node.children.map(cloneUINode)
    };
  }

  if (isMountPointNode(node)) {
    return {
      ...node,
      props: { ...node.props }
    };
  }

  return node;
}

export function findNodeByPath(tree: UINode, path: number[]): UINode | null {
  let current = tree;
  
  for (const index of path) {
    // Only element nodes can have children
    if (isElementNode(current)) {
      if (index >= current.children.length || index < 0) {
        return null;
      }
      current = current.children[index];
    } else {
      // Text nodes and mount points don't have children, so path is invalid
      return null;
    }
  }
  
  return current;
}

export function findParentByPath(tree: UINode, path: number[]): { parent: UIElementNode; index: number } | null {
  if (path.length === 0) return null;
  
  const parentPath = path.slice(0, -1);
  const index = path[path.length - 1];
  
  const parent = parentPath.length === 0 ? tree : findNodeByPath(tree, parentPath);
  
  if (!parent || !isElementNode(parent)) {
    return null;
  }
  
  return { parent, index };
}

export function applyUpdate(tree: UINode, update: UIUpdatePayload): UINode {
  const clonedTree = cloneUINode(tree);
  
  switch (update.type) {
    case 'insert': {
      const parent = findNodeByPath(clonedTree, update.path);
      if (parent && isElementNode(parent)) {
        parent.children.splice(update.data.index, 0, update.data.node);
      }
      break;
    }
    
    case 'remove': {
      const parent = findNodeByPath(clonedTree, update.path);
      if (parent && isElementNode(parent)) {
        parent.children.splice(update.data.index, 1);
      }
      break;
    }
    
    case 'replace': {
      const parentInfo = findParentByPath(clonedTree, update.path);
      if (parentInfo) {
        parentInfo.parent.children[parentInfo.index] = update.data.node;
      } else if (update.path.length === 0) {
        return update.data.node;
      }
      break;
    }
    
    case 'update_props': {
      const node = findNodeByPath(clonedTree, update.path);
      if (node && (isElementNode(node) || isMountPointNode(node))) {
        node.props = { ...node.props, ...update.data.props };
      }
      break;
    }
  }
  
  return clonedTree;
}

export function applyUpdates(tree: UINode, updates: UIUpdatePayload[]): UINode {
  return updates.reduce((currentTree, update) => applyUpdate(currentTree, update), tree);
}