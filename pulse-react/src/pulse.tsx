import React, {
  useEffect,
  useState,
  useMemo,
  createContext,
  useContext,
  type ComponentType,
} from "react";
import { VDOMRenderer } from "./renderer";
import { PulseSocketIOClient } from "./client";
import type { VDOM, ComponentRegistry } from "./vdom";
import { useLocation, useParams, useNavigate } from "react-router";
import type { ServerErrorInfo } from "./messages";
import type { RouteInfo } from "./helpers";

// =================================================================
// Types
// =================================================================

export interface PulseConfig {
  serverAddress: string;
}

// =================================================================
// Context and Hooks
// =================================================================

// Context for the client, provided by PulseProvider
const PulseClientContext = createContext<PulseSocketIOClient | null>(null);

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

const inBrowser = typeof window !== "undefined";

export function PulseProvider({ children, config }: PulseProviderProps) {
  const [connected, setConnected] = useState(true);
  const rrNavigate = useNavigate();

  const client = useMemo(
    () => new PulseSocketIOClient(`${config.serverAddress}`, rrNavigate),
    [config.serverAddress, rrNavigate]
  );

  useEffect(() => client.onConnectionChange(setConnected), [client]);

  useEffect(() => {
    if (inBrowser) {
      client.connect();
      return () => client.disconnect();
    }
  }, [client]);

  return (
    <PulseClientContext.Provider value={client}>
      {!connected && (
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
  const [vdom, setVdom] = useState(initialVDOM);
  const [serverError, setServerError] = useState<ServerErrorInfo | null>(null);

  const location = useLocation();
  const params = useParams();

  const routeInfo = useMemo(() => {
    const { "*": catchall = "", ...pathParams } = params;
    const queryParams = new URLSearchParams(location.search);
    return {
      hash: location.hash,
      pathname: location.pathname,
      query: location.search,
      queryParams: Object.fromEntries(queryParams.entries()),
      pathParams,
      catchall: catchall.length > 0 ? catchall.split("/") : [],
    } satisfies RouteInfo;
  }, [
    location.hash,
    location.pathname,
    location.search,
    JSON.stringify(params),
  ]);

  useEffect(() => {
    if (inBrowser) {
      client.mountView(path, {
        vdom: initialVDOM,
        listener: setVdom,
        routeInfo,
      });
      const offErr = client.onServerError((p, err) => {
        if (p === path) setServerError(err);
      });
      return () => {
        console.log("Unmounting", path)
        offErr();
        client.unmount(path);
      };
    }
    // routeInfo is NOT included here on purpose
  }, [client]);

  useEffect(() => {
    if (inBrowser) {
      client.navigate(path, routeInfo);
    }
  }, [client, path, routeInfo]);

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
      {serverError ? (
        <ServerError error={serverError} />
      ) : (
        <VDOMRenderer node={vdom} />
      )}
    </PulseRenderContext.Provider>
  );
}

function ServerError({ error }: { error: ServerErrorInfo }) {
  return (
    <div
      style={{
        padding: 16,
        border: "1px solid #e00",
        background: "#fff5f5",
        color: "#900",
        fontFamily:
          'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
        whiteSpace: "pre-wrap",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 8 }}>
        Server Error during {error.phase}
      </div>
      {error.message && <div>{error.message}</div>}
      {error.stack && (
        <details open style={{ marginTop: 8 }}>
          <summary>Stack trace</summary>
          <pre style={{ margin: 0 }}>{error.stack}</pre>
        </details>
      )}
    </div>
  );
}
