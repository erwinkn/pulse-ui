import React, {
  useEffect,
  useState,
  useMemo,
  createContext,
  useContext,
  type ComponentType,
} from "react";
import { VDOMRenderer } from "./renderer";
import { PulseClient } from "./client";
import { SocketIOTransport } from "./transport";
import type { VDOM, ComponentRegistry } from "./vdom";

// =================================================================
// Types
// =================================================================

export interface PulseConfig {
  serverAddress: string;
  serverPort: number;
}

// =================================================================
// Context and Hooks
// =================================================================

// Context for the client, provided by PulseProvider
const PulseClientContext = createContext<PulseClient | null>(null);

export const usePulseClient = () => {
  const client = useContext(PulseClientContext);
  if (!client) {
    throw new Error("usePulseClient must be used within a PulseProvider");
  }
  return client;
};

// Context for rendering helpers, provided by PulseView
interface PulseRenderHelpers {
  getCallback: (key: string) => (...args: any[]) => void;
  getComponent: (key: string) => ComponentType<any>;
}

const PulseRenderContext = createContext<PulseRenderHelpers | null>(null);

export const usePulseRenderHelpers = () => {
  const context = useContext(PulseRenderContext);
  if (!context) {
    throw new Error(
      "usePulseRenderHelpers must be used within a PulseRenderContext (provided by <PulseView>)"
    );
  }
  return context;
};

// =================================================================
// Provider
// =================================================================

export interface PulseProviderProps {
  children: React.ReactNode;
  config: PulseConfig;
}

export function PulseProvider({ children, config }: PulseProviderProps) {
  const [connectionError, setConnectionError] = useState(false);

  const client = useMemo(() => {
    const transport = new SocketIOTransport(
      `${config.serverAddress}:${config.serverPort}`
    );
    return new PulseClient(transport);
  }, [config.serverAddress, config.serverPort]);

  useEffect(() => {
    const inBrowser = typeof window !== "undefined";
    if (inBrowser) {
      // Listen for connection state changes
      const unsubscribe = client.onConnectionChange((connected) => {
        setConnectionError(!connected);
      });
      return () => unsubscribe();
    }
  }, [client]);

  return (
    <PulseClientContext.Provider value={client}>
      {connectionError && (
        <div
          style={{
            position: "fixed",
            bottom: "20px",
            right: "20px",
            backgroundColor: "red",
            color: "white",
            padding: "10px",
            borderRadius: "5px",
            zIndex: 1000,
          }}
        >
          Failed to connect to the server.
        </div>
      )}
      {children}
    </PulseClientContext.Provider>
  );
}

// =================================================================
// View
// =================================================================

export interface PulseViewProps {
  initialVDOM: VDOM;
  externalComponents: ComponentRegistry;
  path: string;
}

export function PulseView({
  initialVDOM,
  externalComponents,
  path,
}: PulseViewProps) {
  const client = usePulseClient();
  const [vdom, setVdom] = useState(client.getVDOM(path) ?? initialVDOM);

  useEffect(() => {
    const inBrowser = typeof window !== "undefined";
    if (inBrowser) {
      const unsubscribe = client.subscribe(path, setVdom);
      client.navigate(path);

      return () => {
        unsubscribe();
        client.leave(path);
      };
    }
  }, [client, path]);

  const renderHelpers = useMemo(() => {
    const callbackCache = new Map<string, (...args: any[]) => void>();

    const getCallback = (key: string) => {
      let fn = callbackCache.get(key);
      if (!fn) {
        fn = (...args) => client.invokeCallback(path, key, args);
        callbackCache.set(key, fn);
      }
      return fn;
    };

    const getComponent = (key: string) => {
      const component = externalComponents[key];
      if (!component) {
        throw new Error(`Component with key "${key}" not found.`);
      }
      return component;
    };

    return { getCallback, getComponent };
  }, [client, externalComponents, path]);

  return (
    <PulseRenderContext.Provider value={renderHelpers}>
      <VDOMRenderer node={vdom} />
    </PulseRenderContext.Provider>
  );
}
