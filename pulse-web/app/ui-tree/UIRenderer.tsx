import React, { memo } from 'react';
import type { UINode, UIElementNode } from './types';
import { isElementNode, isTextNode, isFragment, FRAGMENT_TAG } from './types';

interface UIRendererProps {
  node: UINode;
}

const UIElementRenderer = memo<{ node: UIElementNode }>(({ node }) => {
  const { tag, props, children } = node;
  
  // If this is a fragment, render as React Fragment
  if (tag === FRAGMENT_TAG) {
    return (
      <>
        {children.map((child, index) => (
          <UIRenderer 
            key={isElementNode(child) ? (child.key || child.id) : index} 
            node={child} 
          />
        ))}
      </>
    );
  }
  
  // Regular element
  const renderedChildren = children.map((child, index) => (
    <UIRenderer 
      key={isElementNode(child) ? (child.key || child.id) : index} 
      node={child} 
    />
  ));
  
  return React.createElement(tag, props, ...renderedChildren);
});

export const UIRenderer = memo<UIRendererProps>(({ node }) => {
  // Handle text nodes (strings) directly
  if (isTextNode(node)) {
    return <>{node}</>;
  }
  
  // Handle element nodes (including fragments)
  if (isElementNode(node)) {
    return <UIElementRenderer node={node} />;
  }
  
  // Fallback for any unexpected node types
  return null;
});

UIRenderer.displayName = 'UIRenderer';