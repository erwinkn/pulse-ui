import React, { memo } from 'react';
import type { UINode, UIElementNode, UIMountPointNode } from './types';
import { isElementNode, isTextNode, isMountPointNode, isFragment, FRAGMENT_TAG } from './types';
import { useComponent } from './component-registry';

interface UIRendererProps {
  node: UINode;
}

const UIMountPointRenderer = memo<{ node: UIMountPointNode }>(({ node }) => {
  const { componentKey, props } = node;
  const Component = useComponent(componentKey);
  
  return <Component {...props} />;
});

const UIElementRenderer = memo<{ node: UIElementNode }>(({ node }) => {
  const { tag, props, children } = node;
  
  // If this is a fragment, render as React Fragment
  if (tag === FRAGMENT_TAG) {
    return (
      <>
        {children.map((child, index) => (
          <UIRenderer 
            key={getNodeKey(child, index)} 
            node={child} 
          />
        ))}
      </>
    );
  }
  
  // Regular element
  const renderedChildren = children.map((child, index) => (
    <UIRenderer 
      key={getNodeKey(child, index)} 
      node={child} 
    />
  ));
  
  return React.createElement(tag, props, ...renderedChildren);
});

// Helper function to generate keys for React reconciliation
function getNodeKey(node: UINode, index: number): string | number {
  if (isElementNode(node) || isMountPointNode(node)) {
    return node.key || node.id;
  }
  return index;
}

export const UIRenderer = memo<UIRendererProps>(({ node }) => {
  // Handle text nodes (strings) directly
  if (isTextNode(node)) {
    return <>{node}</>;
  }
  
  // Handle mount point nodes
  if (isMountPointNode(node)) {
    return <UIMountPointRenderer node={node} />;
  }
  
  // Handle element nodes (including fragments)
  if (isElementNode(node)) {
    return <UIElementRenderer node={node} />;
  }
  
  // Fallback for any unexpected node types
  return null;
});

UIRenderer.displayName = 'UIRenderer';