import {
	createContext,
	type ReactNode,
	useContext,
	useEffect,
	useLayoutEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import {
	createPulseChannelManager,
	type ChannelBridge,
	type PulseChannelManager,
} from "./channel";
import { type ConnectionStatus, type Directives, PulseSocketIOClient } from "./client";
import { buildRouteInfo, type RouteInfo } from "./helpers";
import type { ServerError } from "./messages";
import { VDOMRenderer } from "./renderer";
import { deserialize } from "./serialize/serializer";
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
	// Unique id of the server-side view
	view: string;
	// Route pattern path (e.g. "/users/:id")
	routePath: string;
	vdom: VDOM;
};

export type PulsePrerender = {
	views: Record<string, PulsePrerenderView>;
	directives: Directives;
};
// =================================================================
// Context and Hooks
// =================================================================

// Context for the client, provided by PulseProvider
const PulseClientContext = createContext<PulseSocketIOClient | null>(null);
const PulsePrerenderContext = createContext<PulsePrerender | null>(null);
export const PulseViewIdContext = createContext<string | null>(null);

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

export const usePulseViewId = () => {
	const viewId = useContext(PulseViewIdContext);
	if (!viewId) {
		throw new Error("usePulseViewId must be used within a PulseView");
	}
	return viewId;
};

export function usePulseChannelManager(): PulseChannelManager {
	const viewId = usePulseViewId();
	return usePulseChannelManagerForView(viewId);
}

export function usePulseChannelManagerForView(viewId: string): PulseChannelManager {
	const client = usePulseClient();
	const manager = useMemo(
		() => createPulseChannelManager(client, viewId),
		[client, viewId],
	);
	const pendingDispose = useRef<{
		manager: PulseChannelManager;
		timer: ReturnType<typeof setTimeout>;
	} | null>(null);
	useEffect(() => {
		if (pendingDispose.current?.manager === manager) {
			clearTimeout(pendingDispose.current.timer);
			pendingDispose.current = null;
		}
		return () => {
			const timer = setTimeout(() => {
				manager.dispose();
				if (pendingDispose.current?.manager === manager) {
					pendingDispose.current = null;
				}
			}, 0);
			pendingDispose.current = { manager, timer };
		};
	}, [manager]);
	return manager;
}

export function usePulseChannel(channelId: string): ChannelBridge | null {
	const manager = usePulseChannelManager();
	const [bridge, setBridge] = useState<ChannelBridge | null>(null);

	useEffect(() => {
		if (!channelId) {
			throw new Error("usePulseChannel requires a non-empty channelId");
		}
		const lease = manager.acquire(channelId);
		setBridge(lease.bridge);
		return () => {
			setBridge((current) => (current === lease.bridge ? null : current));
			lease.release();
		};
	}, [manager, channelId]);

	return bridge;
}

// =================================================================
// Provider
// =================================================================

export interface PulseProviderProps {
	children: ReactNode;
	config: PulseConfig;
	prerender: PulsePrerender;
}

function useRouteInfo(): RouteInfo {
	const location = useLocation();
	const params = useParams();
	// biome-ignore lint/correctness/useExhaustiveDependencies: using hacky deep equality for params
	return useMemo(() => {
		const { "*": catchall = "", ...pathParams } = params;
		return buildRouteInfo(
			location,
			pathParams,
			catchall.length > 0 ? catchall.split("/") : [],
		);
	}, [location.hash, location.pathname, location.search, JSON.stringify(params)]);
}

const inBrowser = typeof window !== "undefined";
const useIsomorphicLayoutEffect = inBrowser ? useLayoutEffect : useEffect;

function reportConnectionError(err: unknown) {
	console.error("[PulseProvider] Connection failed:", err);
}

export function PulseProvider({ children, config, prerender }: PulseProviderProps) {
	const [status, setStatus] = useState<ConnectionStatus>("ok");
	const navigate = useNavigate();
	const { directives } = prerender;

	// biome-ignore lint/correctness/useExhaustiveDependencies: another useEffect syncs the directives without recreating the client
	const client = useMemo(() => {
		return new PulseSocketIOClient(
			config.serverAddress,
			directives,
			navigate,
			config.connectionStatus,
		);
	}, [config.serverAddress, navigate, config.connectionStatus]);
	useEffect(() => client.setDirectives(directives), [client, directives]);

	useEffect(() => {
		if (!inBrowser) return;

		const handleConnectionChange = (newStatus: ConnectionStatus) => {
			setStatus(newStatus);
		};

		const unsubscribe = client.onConnectionChange(handleConnectionChange);

		// Start connection attempt
		void client.connect().catch(reportConnectionError);

		return () => {
			unsubscribe();
			client.disconnect();
		};
	}, [client]);

	useEffect(() => {
		if (!inBrowser) return;

		const handleVisibilityChange = () => {
			if (document.visibilityState === "hidden") {
				client.suspend();
				return;
			}
			void client.resume().catch(reportConnectionError);
		};

		document.addEventListener("visibilitychange", handleVisibilityChange);
		handleVisibilityChange();
		return () => {
			document.removeEventListener("visibilitychange", handleVisibilityChange);
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
	const viewId = initialView.view;
	const channels = usePulseChannelManagerForView(viewId);
	const renderer = useMemo(
		() => new VDOMRenderer(client, channels, viewId, registry),
		[client, channels, viewId, registry],
	);
	const [tree, setTree] = useState<ReactNode>(() => renderer.init(initialView));
	const [serverError, setServerError] = useState<ServerError | null>(null);

	const routeInfo = useRouteInfo();

	// biome-ignore lint/correctness/useExhaustiveDependencies: We don't want to detach on navigation, so another useEffect syncs the routeInfo on navigation.
	useEffect(() => {
		if (inBrowser) {
			client.attach(viewId, {
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
				deserializeMessage: (data) =>
					deserialize(data, { coerceNullsToUndefined: true, renderer }),
			});
			return () => {
				renderer.clearPendingCallbacks();
				renderer.dispose();
				client.detach(viewId);
			};
		}
		//  routeInfo is NOT included here on purpose
	}, [client, renderer, viewId]);

	useEffect(() => {
		if (inBrowser) {
			client.updateRoute(viewId, routeInfo);
		}
	}, [client, viewId, routeInfo]);
	// Hack for our current prerendering setup on client-side navigation. Will be improved soon
	const hasRendered = useRef(false);
	useIsomorphicLayoutEffect(() => {
		// First rendering pass, no need to update the tree
		if (!hasRendered.current) {
			hasRendered.current = true;
		}
		// 2nd+ rendering pass. Happens when a route stays mounted on navigation.
		else {
			setTree(renderer.init(initialView));
		}
		// Note: Do NOT reset hasRendered in cleanup. The cleanup runs when effect 
		// deps change and at least once on mount with strict mode,
		// not just on unmount, which would cause subsequent runs to skip setTree.
	}, [initialView, renderer]);

	if (serverError) {
		return <ServerErrorPopup error={serverError} />;
	}

	return <PulseViewIdContext.Provider value={viewId}>{tree}</PulseViewIdContext.Provider>;
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
