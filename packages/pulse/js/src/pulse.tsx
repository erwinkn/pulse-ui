import {
	createContext,
	type ReactNode,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { type ConnectionStatus, type Directives, PulseSocketIOClient } from "./client";
import type { RouteInfo } from "./helpers";
import type { ServerError } from "./messages";
import { VDOMRenderer } from "./renderer";
import type { VDOM } from "./vdom";

// =================================================================
// Types
// =================================================================

export interface ConnectionStatusConfig {
	initialConnectingDelay: number;
	initialErrorDelay: number;
	reconnectErrorDelay: number;
}

export interface PulseConfig {
	serverAddress: string;
	connectionStatus: ConnectionStatusConfig;
	apiPrefix: string;
}

export type PulsePrerenderView = {
	vdom: VDOM;
};

export type PulsePrerender = {
	renderId: string;
	views: Record<string, PulsePrerenderView>;
	directives: Directives;
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
	children: ReactNode;
	config: PulseConfig;
	prerender: PulsePrerender;
}

const inBrowser = typeof window !== "undefined";

export function PulseProvider({ children, config, prerender }: PulseProviderProps) {
	const [status, setStatus] = useState<ConnectionStatus>("ok");
	const rrNavigate = useNavigate();
	const { directives } = prerender;

	// biome-ignore lint/correctness/useExhaustiveDependencies: another useEffect syncs the directives without recreating the client
	const client = useMemo(() => {
		return new PulseSocketIOClient(
			config.serverAddress,
			directives,
			rrNavigate,
			config.connectionStatus,
		);
	}, [config.serverAddress, rrNavigate, config.connectionStatus]);
	useEffect(() => client.setDirectives(directives), [client, directives]);

	useEffect(() => {
		if (!inBrowser) return;

		const handleConnectionChange = (newStatus: ConnectionStatus) => {
			setStatus(newStatus);
		};

		const unsubscribe = client.onConnectionChange(handleConnectionChange);

		// Start connection attempt
		client.connect();

		return () => {
			unsubscribe();
			client.disconnect();
		};
	}, [client]);

	const getStatusMessage = () => {
		switch (status) {
			case "connecting":
				return "Connecting...";
			case "reconnecting":
				return "Reconnecting...";
			case "error":
				return "Failed to connect to the server.";
			// "ok" falls through to default
			default:
				return null;
		}
	};

	const statusMessage = getStatusMessage();

	return (
		<PulseClientContext.Provider value={client}>
			<PulsePrerenderContext.Provider value={prerender}>
				{statusMessage && (
					<div
						style={{
							position: "fixed",
							bottom: "20px",
							right: "20px",
							backgroundColor: status === "error" ? "red" : "#666",
							color: "white",
							padding: "10px",
							borderRadius: "5px",
							zIndex: 1000,
						}}
					>
						{statusMessage}
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
	path: string;
	registry: Record<string, unknown>;
}

export function PulseView({ path, registry }: PulseViewProps) {
	const client = usePulseClient();
	const initialView = usePulsePrerender(path);
	const renderer = useMemo(
		() => new VDOMRenderer(client, path, registry),
		[client, path, registry],
	);
	const [tree, setTree] = useState<ReactNode>(() => renderer.init(initialView));
	const [serverError, setServerError] = useState<ServerError | null>(null);

	const location = useLocation();
	const params = useParams();

	// biome-ignore lint/correctness/useExhaustiveDependencies: using hacky deep equality for params
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
	}, [location.hash, location.pathname, location.search, JSON.stringify(params)]);

	// biome-ignore lint/correctness/useExhaustiveDependencies: We don't want to detach on navigation, so another useEffect syncs the routeInfo on navigation.
	useEffect(() => {
		if (inBrowser) {
			client.attach(path, {
				routeInfo,
				onInit: (view) => {
					setTree(renderer.init(view));
					setServerError(null);
				},
				onUpdate: (ops) => {
					setTree((prev) => (prev == null ? prev : renderer.applyUpdates(prev, ops)));
					setServerError(null);
				},
				onJsExec: (msg) => {
					let result: any;
					let error: string | null = null;
					try {
						result = renderer.evaluateExpr(msg.expr);
					} catch (e) {
						error = e instanceof Error ? e.message : String(e);
					}
					client.sendJsResult(msg.id, result, error);
				},
				onServerError: setServerError,
			});
			return () => {
				client.detach(path);
			};
		}
		//  routeInfo is NOT included here on purpose
	}, [client, renderer, path]);

	useEffect(() => {
		if (inBrowser) {
			client.updateRoute(path, routeInfo);
		}
	}, [client, path, routeInfo]);
	// Hack for our current prerendering setup on client-side navigation. Will be improved soon
	const hasRendered = useRef(false);
	useEffect(() => {
		// First rendering pass, no need to update the tree
		if (!hasRendered.current) {
			hasRendered.current = true;
		}
		// 2nd+ rendering pass. Happens when a route stays mounted on navigation.
		else {
			setTree(renderer.init(initialView));
		}
		return () => {
			hasRendered.current = false;
		};
	}, [initialView, renderer]);

	if (serverError) {
		return <ServerErrorPopup error={serverError} />;
	}

	return tree;
}

function ServerErrorPopup({ error }: { error: ServerError }) {
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
			<div style={{ fontWeight: 700, marginBottom: 8 }}>Server Error during {error.phase}</div>
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
