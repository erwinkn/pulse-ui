import React, { useEffect, useRef } from 'react';
import { UIRenderer } from './UIRenderer';
import { useReactiveUITree } from './useReactiveUITree';
import type { UINode } from './types';
import type { Transport, TransportMessage } from './transport';
import { WebSocketTransport } from './transport';

export interface ReactiveUIContainerProps {
  initialTree: UINode;
  transport?: Transport;
  onMessage?: (message: TransportMessage) => void;
  // Legacy props for backward compatibility
  websocketUrl?: string;
  onWebSocketMessage?: (data: any) => void;
}

export function ReactiveUIContainer({ 
  initialTree, 
  transport,
  onMessage,
  // Legacy props
  websocketUrl,
  onWebSocketMessage
}: ReactiveUIContainerProps) {
  const { tree, applyBatchUpdates, setTree } = useReactiveUITree({ initialTree });
  const transportRef = useRef<Transport | null>(null);
  
  useEffect(() => {
    // Use provided transport or create WebSocket transport
    const activeTransport = transport || (websocketUrl ? new WebSocketTransport(websocketUrl) : null);
    
    if (!activeTransport) return;
    
    transportRef.current = activeTransport;
    
    activeTransport.onMessage((message) => {
      if (onMessage) {
        onMessage(message);
      }
      
      // Legacy callback support
      if (onWebSocketMessage) {
        onWebSocketMessage(message);
      }
      
      if (message.type === 'ui_updates' && Array.isArray(message.updates)) {
        applyBatchUpdates(message.updates);
      } else if (message.type === 'ui_tree' && message.tree) {
        setTree(message.tree);
      }
    });
    
    return () => {
      if (transportRef.current && !transport) {
        // Only close if we created the transport ourselves
        transportRef.current.close();
      }
      transportRef.current = null;
    };
  }, [transport, websocketUrl, applyBatchUpdates, setTree, onMessage, onWebSocketMessage]);
  
  return <UIRenderer node={tree} />;
}