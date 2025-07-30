import React, { memo } from "react";
import type { UINode, UIElementNode } from "./tree";
import {
  isElementNode,
  isTextNode,
  isMountPointNode,
  isFragment,
  FRAGMENT_TAG,
  getMountPointComponentKey,
} from "./tree";
import { useComponent } from "./component-registry";

interface UIRendererProps {
  node: UINode;
}

const UIMountPointRenderer = memo<{ node: UIElementNode }>(({ node }) => {
  const { props, children } = node;
  const componentKey = getMountPointComponentKey(node);
  const Component = useComponent(componentKey);

  // Render children and pass them to the component
  const renderedChildren = children.map((child, index) => (
    <UIRenderer key={getNodeKey(child, index)} node={child} />
  ));

  return <Component {...props}>{renderedChildren}</Component>;
});

const UIElementRenderer = memo<{ node: UIElementNode }>(({ node }) => {
  const { tag, props, children } = node;

  // If this is a mount point, render the mounted component
  if (isMountPointNode(node)) {
    return <UIMountPointRenderer node={node} />;
  }

  // If this is a fragment, render as React Fragment
  if (tag === FRAGMENT_TAG) {
    return (
      <>
        {children.map((child, index) => (
          <UIRenderer key={getNodeKey(child, index)} node={child} />
        ))}
      </>
    );
  }

  // Regular element
  const renderedChildren = children.map((child, index) => (
    <UIRenderer key={getNodeKey(child, index)} node={child} />
  ));

  return React.createElement(tag, props, ...renderedChildren);
});

// Helper function to generate keys for React reconciliation
function getNodeKey(node: UINode, index: number): string | number {
  if (isElementNode(node)) {
    return node.key || index;
  }
  return index;
}

export const UIRenderer = memo<UIRendererProps>(({ node }) => {
  // Handle text nodes (strings) directly
  if (isTextNode(node)) {
    return <>{node}</>;
  }

  // Handle element nodes (including fragments and mount points)
  if (isElementNode(node)) {
    return <UIElementRenderer node={node} />;
  }

  // Fallback for any unexpected node types
  return null;
});

UIRenderer.displayName = "UIRenderer";
