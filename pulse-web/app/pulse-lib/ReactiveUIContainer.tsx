import React, { useEffect, useRef, useMemo } from "react";
import { UIRenderer } from "./UIRenderer";
import { useReactiveUITree } from "./useReactiveUITree";
import type { UINode } from "./tree";
import type { Transport, TransportMessage } from "./transport";

export interface ReactiveUIContainerProps {
  initialTree: UINode;
  callbackInfo?: Record<string, any>;
  transport?: Transport;
}

export function ReactiveUIContainer({
  initialTree,
  callbackInfo,
  transport,
}: ReactiveUIContainerProps) {
  const transportRef = useRef<Transport | null>(null);

  // Process the initial tree to replace callback placeholders with actual functions
  const processedTree = useMemo(() => {
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

  useEffect(() => {
    if (!transport) return;

    transportRef.current = transport;

    transport.onMessage((message) => {
      console.log("ReactiveUIContainer received message:", message);
      
      if (message.type === "ui_updates" && Array.isArray(message.updates)) {
        console.log("Applying batch updates:", message.updates);
        applyBatchUpdates(message.updates);
      } else if (message.type === "ui_tree" && message.tree) {
        console.log("Setting new tree:", message.tree);
        setTree(message.tree);
      }
    });

    return () => {
      transportRef.current = null;
    };
  }, [transport, applyBatchUpdates, setTree]);

  return <UIRenderer node={tree} />;
}
