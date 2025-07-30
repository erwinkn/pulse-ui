import React, { useState, useRef, useImperativeHandle, forwardRef } from "react";
import { ReactiveUIContainer } from "~/pulse-lib/ReactiveUIContainer";
import { ComponentRegistryProvider } from "~/pulse-lib/component-registry";
import { EventEmitterTransport } from "~/pulse-lib/transport";
import { useReactiveUITree } from "~/pulse-lib/useReactiveUITree";
import { UIRenderer } from "~/pulse-lib/UIRenderer";
import type { ComponentType } from "react";
import type { UIUpdatePayload, UINode } from "~/pulse-lib/tree";

// No components needed for this route
const componentRegistry: Record<string, ComponentType<any>> = {};

// Custom testable UI container that exposes update methods directly
interface TestableUIContainerProps {
  initialTree: UINode;
  callbackInfo?: Record<string, any>;
  transport?: EventEmitterTransport;
  onUpdateMethodsReady?: (methods: { applyBatchUpdates: (updates: UIUpdatePayload[]) => void }) => void;
}

const TestableUIContainer = forwardRef<any, TestableUIContainerProps>(
  ({ initialTree, callbackInfo, transport, onUpdateMethodsReady }, ref) => {
    const transportRef = useRef<EventEmitterTransport | null>(null);

    // Process the initial tree to replace callback placeholders with actual functions
    const processedTree = React.useMemo(() => {
      if (!callbackInfo) return initialTree;

      function processNode(node: UINode): UINode {
        if (typeof node === "string") return node;

        const processedProps: Record<string, any> = {};

        // Process props to replace callback placeholders
        for (const [propName, propValue] of Object.entries(node.props || {})) {
          if (
            typeof propValue === "string" &&
            propValue.startsWith("__callback:")
          ) {
            const callbackKey = propValue.replace("__callback:", "");
            // Create a function that sends a callback message when called
            processedProps[propName] = () => {
              if (transportRef.current) {
                transportRef.current.send({
                  type: "callback_invoke",
                  callback_key: callbackKey,
                  request_id: Math.random().toString(36).substr(2, 9),
                });
              } else {
                console.warn("Transport not available for callback:", callbackKey);
              }
            };
          } else {
            processedProps[propName] = propValue;
          }
        }

        // Process children recursively
        const processedChildren =
          node.children?.map((child) => processNode(child)) || [];

        return {
          ...node,
          props: processedProps,
          children: processedChildren,
        };
      }

      return processNode(initialTree);
    }, [initialTree, callbackInfo]);

    const { tree, applyBatchUpdates, setTree } = useReactiveUITree({
      initialTree: processedTree,
    });

    // Expose update methods to parent
    React.useEffect(() => {
      if (onUpdateMethodsReady) {
        onUpdateMethodsReady({ applyBatchUpdates });
      }
    }, [applyBatchUpdates, onUpdateMethodsReady]);

    React.useEffect(() => {
      if (!transport) return;
      transportRef.current = transport;
      
      return () => {
        transportRef.current = null;
      };
    }, [transport]);

    return <UIRenderer node={tree} />;
  }
);

const initialTree = {
  "tag": "div",
  "props": {
    "style": {
      "fontFamily": "Arial, sans-serif",
      "padding": "20px"
    }
  },
  "children": [
    {
      "tag": "h1",
      "props": {
        "style": { "color": "#333", "marginBottom": "20px" }
      },
      "children": ["VDOM Update Test"]
    },
    {
      "tag": "div",
      "props": {
        "id": "test-container",
        "style": {
          "border": "2px solid #ccc",
          "padding": "20px",
          "marginBottom": "20px",
          "borderRadius": "8px"
        }
      },
      "children": [
        {
          "tag": "h2",
          "props": {},
          "children": ["Dynamic Content Area"]
        },
        {
          "tag": "p",
          "key": "item-1",
          "props": { "style": { "color": "blue" } },
          "children": ["Item 1 (with key)"]
        },
        {
          "tag": "p",
          "props": { "style": { "color": "green" } },
          "children": ["Item 2 (position-based)"]
        }
      ]
    },
    {
      "tag": "div",
      "props": {
        "style": {
          "display": "grid",
          "gridTemplateColumns": "repeat(2, 1fr)",
          "gap": "10px",
          "marginBottom": "20px"
        }
      },
      "children": [
        {
          "tag": "button",
          "props": {
            "onClick": "__callback:insert-item",
            "style": {
              "padding": "10px",
              "backgroundColor": "#4CAF50",
              "color": "white",
              "border": "none",
              "borderRadius": "4px",
              "cursor": "pointer"
            }
          },
          "children": ["Insert Item"]
        },
        {
          "tag": "button",
          "props": {
            "onClick": "__callback:remove-item",
            "style": {
              "padding": "10px",
              "backgroundColor": "#f44336",
              "color": "white",
              "border": "none",
              "borderRadius": "4px",
              "cursor": "pointer"
            }
          },
          "children": ["Remove Last Item"]
        },
        {
          "tag": "button",
          "props": {
            "onClick": "__callback:replace-item",
            "style": {
              "padding": "10px",
              "backgroundColor": "#ff9800",
              "color": "white",
              "border": "none",
              "borderRadius": "4px",
              "cursor": "pointer"
            }
          },
          "children": ["Replace First Item"]
        },
        {
          "tag": "button",
          "props": {
            "onClick": "__callback:update-props",
            "style": {
              "padding": "10px",
              "backgroundColor": "#2196F3",
              "color": "white",
              "border": "none",
              "borderRadius": "4px",  
              "cursor": "pointer"
            }
          },
          "children": ["Update Container Props"]
        }
      ]
    },
    {
      "tag": "div",
      "props": {
        "style": {
          "backgroundColor": "#f5f5f5",
          "padding": "15px",
          "borderRadius": "4px"
        }
      },
      "children": [
        {
          "tag": "h3",
          "props": {},
          "children": ["Instructions:"]
        },
        {
          "tag": "ul",
          "props": {},
          "children": [
            {
              "tag": "li",
              "props": {},
              "children": ["Insert Item: Adds a new item to the dynamic content area"]
            },
            {
              "tag": "li", 
              "props": {},
              "children": ["Remove Last Item: Removes the last item from the list"]
            },
            {
              "tag": "li",
              "props": {},
              "children": ["Replace First Item: Replaces the first item with new content"]
            },
            {
              "tag": "li",
              "props": {},
              "children": ["Update Container Props: Changes the container's border color"]
            }
          ]
        }
      ]
    },
    {
      "tag": "p",
      "props": {
        "style": { "marginTop": "20px" }
      },
      "children": [
        {
          "tag": "a",
          "props": {
            "href": "/",
            "style": { "color": "#2196F3", "textDecoration": "none" }
          },
          "children": ["← Back to Home"]
        }
      ]
    }
  ]
};

let itemCounter = 3; // Start from 3 since we have items 1 and 2

export default function TestUpdatesRoute() {
  const transportRef = useRef<EventEmitterTransport | null>(null);
  const updateMethodsRef = useRef<{ applyBatchUpdates: (updates: UIUpdatePayload[]) => void } | null>(null);

  // Initialize transport on first render
  if (!transportRef.current) {
    transportRef.current = new EventEmitterTransport();
  }

  const transport = transportRef.current;

  // Define the update functions - now call applyBatchUpdates directly
  const applyInsertUpdate = () => {
    const insertUpdate: UIUpdatePayload = {
      type: "insert",
      path: [1], // Target the test-container div (index 1 in root children)
      data: {
        node: {
          "tag": "p",
          "key": `item-${itemCounter}`,
          "props": { 
            "style": { 
              "color": "purple",
              "fontWeight": "bold" 
            } 
          },
          "children": [`New Item ${itemCounter} (inserted with key)`]
        },
        index: 2 // Insert at index 2 (after h2 and the first two paragraphs)
      }
    };

    console.log("Directly calling applyBatchUpdates with insert update");
    updateMethodsRef.current?.applyBatchUpdates([insertUpdate]);
    itemCounter++;
  };

  const applyRemoveUpdate = () => {
    const removeUpdate: UIUpdatePayload = {
      type: "remove", 
      path: [1], // Target the test-container div
      data: {
        index: 3 // Remove item at index 3
      }
    };

    console.log("Directly calling applyBatchUpdates with remove update");
    updateMethodsRef.current?.applyBatchUpdates([removeUpdate]);
  };

  const applyReplaceUpdate = () => {
    const replaceUpdate: UIUpdatePayload = {
      type: "replace",
      path: [1, 1], // Target first paragraph in test-container (h2 is at index 0, first p is at index 1)
      data: {
        node: {
          "tag": "div",
          "props": { 
            "style": { 
              "backgroundColor": "yellow",
              "padding": "10px", 
              "borderRadius": "4px"
            } 
          },
          "children": ["🎉 Replaced content! This was originally 'Item 1'"]
        }
      }
    };

    console.log("Directly calling applyBatchUpdates with replace update");
    updateMethodsRef.current?.applyBatchUpdates([replaceUpdate]);
  };

  const applyUpdatePropsUpdate = () => {
    const updatePropsUpdate: UIUpdatePayload = {
      type: "update_props",
      path: [1], // Target the test-container div
      data: {
        props: {
          "style": {
            "border": "3px solid #ff4444",
            "padding": "20px",
            "marginBottom": "20px", 
            "borderRadius": "8px",
            "backgroundColor": "#ffe6e6"
          }
        }
      }
    };

    console.log("Directly calling applyBatchUpdates with update props");
    updateMethodsRef.current?.applyBatchUpdates([updatePropsUpdate]);
  };

  // Mock callback info - maps callback placeholders to callback keys
  const callbackInfo = {
    "test-node": {
      "callbacks": {
        "onClick": "insert-item"
      }
    }
  };

  // Handle callback messages
  React.useEffect(() => {
    const handleMessage = (message: any) => {
      console.log("Test route received message:", message);
      
      if (message.type === "callback_invoke") {
        switch (message.callback_key) {
          case "insert-item":
            applyInsertUpdate();
            break;
          case "remove-item":
            applyRemoveUpdate();
            break;
          case "replace-item":
            applyReplaceUpdate();
            break;
          case "update-props":
            applyUpdatePropsUpdate();
            break;
          default:
            console.log("Unknown callback:", message.callback_key);
        }
      }
    };

    transport.onMessage(handleMessage);

    return () => {
      transport.close();
    };
  }, [transport]);

  return (
    <div>
      <ComponentRegistryProvider registry={componentRegistry}>
        <TestableUIContainer
          initialTree={initialTree}
          callbackInfo={callbackInfo}
          transport={transport}
          onUpdateMethodsReady={(methods) => {
            updateMethodsRef.current = methods;
          }}
        />
      </ComponentRegistryProvider>
    </div>
  );
}