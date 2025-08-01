import React, {
  useEffect,
  useState,
  useMemo,
  createContext,
  useContext,
  useCallback,
  type ComponentType,
} from "react";
import { VDOMRenderer } from "./renderer";
import { PulseClient } from "./client";
import type { Transport } from "./transport";
import type { VDOM, VDOMNode } from "./vdom";
export interface ComponentRegistry {
  [key: string]: ComponentType<any>;
}

export interface PulseConfig {
  serverAddress: string;
  serverPort: number;
}

export interface PulseInit {
  route: string;
  initialVDOM: VDOM;
  externalComponents: ComponentRegistry;
  transport: Transport;
}

export interface PulseRendererProps extends PulseInit {
  config: PulseConfig;
}

interface PulseContextValue {
  getCallback: (key: string) => (...args: any[]) => void;
  getComponent: (key: string) => ComponentType<any>;
}

const PulseContext = createContext<PulseContextValue | undefined>(undefined);

export const usePulse = () => {
  const context = useContext(PulseContext);
  if (!context) {
    throw new Error("usePulse must be used within a Pulse provider");
  }
  return context;
};

export function Pulse({
  transport,
  initialVDOM,
  externalComponents,
  route = "/",
}: PulseRendererProps) {
  const client = useMemo(
    () => new PulseClient(transport, initialVDOM),
    [transport, initialVDOM]
  );
  const [vdom, setVdom] = useState(client.getVDOM());

  const callbackCache = useMemo(
    () => new Map<string, (...args: any[]) => void>(),
    []
  );

  // only callbacks without args for now
  const getCallback = useCallback(
    (key: string) => {
      let fn = callbackCache.get(key);
      if (!fn) {
        fn = () => client.invokeCallback(key);
        callbackCache.set(key, fn);
      }
      return fn;
    },
    [client, callbackCache]
  );

  const getComponent = useCallback(
    (key: string) => {
      const component = externalComponents[key];
      if (!component) {
        throw new Error(`Component with key "${key}" not found.`);
      }
      return component;
    },
    [externalComponents]
  );

  useEffect(() => {
    // Subscribe to VDOM updates from the client
    const unsubscribe = client.subscribe(setVdom);
    client.connect(route);
    return () => {
      unsubscribe();
      client.disconnect();
    };
  }, [client, route]);

  const contextValue = useMemo(
    () => ({ getCallback, getComponent }),
    [getCallback, getComponent]
  );

  return (
    <PulseContext.Provider value={contextValue}>
      <VDOMRenderer node={vdom} />
    </PulseContext.Provider>
  );
}
