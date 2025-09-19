import React, {
  useEffect,
  useState,
  useMemo,
  createContext,
  useContext,
  type ComponentType,
} from "react";
import { VDOMRenderer, applyUpdates } from "./renderer";
import { PulseSocketIOClient } from "./client";
import type { VDOM, ComponentRegistry, RegistryEntry } from "./vdom";
import { useLocation, useParams, useNavigate } from "react-router";
import type { ServerErrorInfo } from "./messages";
import type { RouteInfo } from "./helpers";

// =================================================================
// Types
// =================================================================

export interface PulseConfig {
  serverAddress: string;
}

export type PulsePrerender = {
  renderId: string;
  views: Record<string, VDOM>;
};
// =================================================================
// Context and Hooks
// =================================================================

// Context for the client, provided by PulseProvider
const PulseClientContext = createContext<PulseSocketIOClient | null>(null);
const PulsePrerenderContext = createContext<PulsePrerender | null>(null);

export const usePulseClient = () => {
  const client = useContext(PulseClientContext);
  if (!client) {
    throw new Error("usePulseClient must be used within a PulseProvider");
  }
  return client;
};

export const usePulsePrerender = (path: string) => {
  const ctx = useContext(PulsePrerenderContext);
  if (!ctx) {
    throw new Error("usePulsePrerender must be used within a PulseProvider");
  }
  const view = ctx.views[path];
  if (!view) {
    throw new Error(`No prerender found for '${path}'`);
  }
  return view;
};

// =================================================================
// Provider
// =================================================================

export interface PulseProviderProps {
  children: React.ReactNode;
  config: PulseConfig;
  prerender: PulsePrerender;
}

const inBrowser = typeof window !== "undefined";

export function PulseProvider({
  children,
  config,
  prerender,
}: PulseProviderProps) {
  const [connected, setConnected] = useState(true);
  const rrNavigate = useNavigate();
  const { renderId } = prerender;

  const client = useMemo(
    () => new PulseSocketIOClient(config.serverAddress, renderId, rrNavigate),
    [config.serverAddress, rrNavigate, renderId]
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
      <PulsePrerenderContext.Provider value={prerender}>
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
      </PulsePrerenderContext.Provider>
    </PulseClientContext.Provider>
  );
}

// =================================================================
// View
// =================================================================

export interface PulseViewProps {
  externalComponents: ComponentRegistry;
  path: string;
}

export function PulseView({ externalComponents, path }: PulseViewProps) {
  const client = usePulseClient();
  const initialVDOM = usePulsePrerender(path);
  const renderer = useMemo(
    () => new VDOMRenderer(client, path, externalComponents),
    [client, path, externalComponents]
  );
  const [tree, setTree] = useState<React.ReactNode>(() =>
    renderer.renderNode(initialVDOM)
  );
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
        routeInfo,
        onInit: (vdom) => {
          setTree(renderer.renderNode(vdom));
        },
        onUpdate: (ops) => {
          setTree((prev) =>
            prev == null ? prev : applyUpdates(prev, ops, renderer)
          );
        },
      });
      const offErr = client.onServerError((p, err) => {
        if (p === path) setServerError(err);
      });
      return () => {
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

  if (serverError) {
    return <ServerError error={serverError} />;
  }

  return tree;
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
