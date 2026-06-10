import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useLayoutEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	createPulseChannelManager,
	type ChannelBridge,
	type PulseChannelManager,
} from "./channel";
import { type ConnectionStatus, type Directives, PulseSocketIOClient } from "./client";
import { buildRouteInfo, type RouteInfo } from "./helpers";
import type { ServerError, ServerInitMessage, ServerNavigateResultMessage } from "./messages";
import { VDOMRenderer } from "./renderer";
import {
	type NavigationTarget,
	type PulseRoute,
	PulseRouterProvider,
	PulseRoutes,
	type RouteLoaderMap,
	useNavigate,
	useRouteInfo,
} from "./router";
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
	client: PulseSocketIOClient;
	prerender: PulsePrerender;
}

const inBrowser = typeof window !== "undefined";
const useIsomorphicLayoutEffect = inBrowser ? useLayoutEffect : useEffect;

function reportConnectionError(err: unknown) {
	console.error("[PulseProvider] Connection failed:", err);
}

export function PulseProvider({ children, client, prerender }: PulseProviderProps) {
	const [status, setStatus] = useState<ConnectionStatus>("ok");
	const { directives } = prerender;

	useEffect(() => client.setDirectives(directives ?? {}), [client, directives]);

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

// =================================================================
// App shell
// =================================================================

export interface PulseAppProps {
	routes: PulseRoute[];
	routeLoaders: RouteLoaderMap;
	config: PulseConfig;
	prerender: PulsePrerender;
	/** URL of the initial request; required for SSR. */
	url?: string;
}

const DIRECTIVES_KEY = "__PULSE_DIRECTIVES";
// Client-side cache lifetime for prefetched views. Must stay below the
// server's pending-view TTL (60s) so a consumed prefetch always attaches to a
// live view.
const PREFETCH_TTL_MS = 30_000;

function readStoredDirectives(): Directives {
	if (!inBrowser || typeof sessionStorage === "undefined") {
		return {};
	}
	try {
		return JSON.parse(sessionStorage.getItem(DIRECTIVES_KEY) ?? "{}") as Directives;
	} catch {
		return {};
	}
}

function persistDirectives(directives: Directives | undefined) {
	if (!inBrowser || typeof sessionStorage === "undefined" || !directives) {
		return;
	}
	sessionStorage.setItem(DIRECTIVES_KEY, JSON.stringify(directives));
}

type NavigationViews = {
	status: "ok" | "redirect" | "notFound" | "error";
	redirect?: string;
	views?: Record<string, ServerInitMessage | null>;
	directives?: Directives;
};

async function fetchPrerenderViews(
	config: PulseConfig,
	paths: string[],
	routeInfo: RouteInfo,
): Promise<NavigationViews> {
	const directives = readStoredDirectives();
	const headers: Record<string, string> = { "content-type": "application/json" };
	for (const [key, value] of Object.entries(directives.headers ?? {})) {
		headers[key] = value;
	}
	const res = await fetch(config.serverAddress + config.apiPrefix + "/prerender", {
		method: "POST",
		headers,
		credentials: "include",
		body: JSON.stringify({ paths, routeInfo }),
	});
	if (!res.ok) {
		throw new Error(`Prerender request failed with status ${res.status}`);
	}
	const body = await res.json();
	if (body.redirect) {
		return { status: "redirect", redirect: body.redirect };
	}
	if (body.notFound) {
		return { status: "notFound" };
	}
	const prerender = deserialize(body) as PulsePrerender;
	return {
		status: "ok",
		views: prerender.views as Record<string, ServerInitMessage | null>,
		directives: prerender.directives,
	};
}

/**
 * Merge a navigation result into the current view set. Entries the server
 * marked as reused (null) keep their identity so live views stay mounted and
 * their state persists across the navigation.
 */
function mergeNavigationViews(
	current: Record<string, PulsePrerenderView>,
	incoming: Record<string, ServerInitMessage | null>,
): Record<string, PulsePrerenderView> {
	const next: Record<string, PulsePrerenderView> = {};
	for (const [path, entry] of Object.entries(incoming)) {
		// Wire deserialization may coerce null reuse markers to undefined.
		if (entry == null) {
			const existing = current[path];
			if (!existing) {
				throw new Error(
					`[Pulse] Server reused the view for '${path}' but the client has no entry for it`,
				);
			}
			next[path] = existing;
		} else {
			next[path] = entry;
		}
	}
	return next;
}

function PulseFrameworkNavigationBinder({ client }: { client: PulseSocketIOClient }) {
	const navigate = useNavigate();
	useEffect(() => {
		client.setFrameworkNavigate(navigate);
	}, [client, navigate]);
	return null;
}

/**
 * The Pulse application shell: router + socket client + route views.
 *
 * Navigation is server-driven: link clicks ask the Python server for the
 * target's views over the WebSocket (falling back to HTTP prerender when the
 * socket is down), and hovering a link prefetches both the route's JS chunks
 * and its server-rendered views.
 */
export function PulseApp({ routes, routeLoaders, config, prerender, url }: PulseAppProps) {
	const [current, setCurrent] = useState(prerender);
	useEffect(() => {
		persistDirectives(current.directives);
	}, [current]);

	const client = useMemo(
		() =>
			new PulseSocketIOClient(
				config.serverAddress,
				prerender.directives ?? {},
				config.connectionStatus,
			),
		// biome-ignore lint/correctness/useExhaustiveDependencies: directives are synced by PulseProvider without recreating the client
		[config.serverAddress, config.connectionStatus],
	);

	const prefetches = useRef(
		new Map<string, { at: number; promise: Promise<ServerNavigateResultMessage> }>(),
	);

	const requestViews = useCallback(
		async (target: NavigationTarget, prefetch: boolean): Promise<NavigationViews> => {
			const routeInfo = buildRouteInfo(
				target.location,
				target.match.params,
				target.match.catchall,
			);
			if (client.isConnected()) {
				return client.navigateViews(routeInfo, { prefetch });
			}
			const paths = target.match.matches.map((route) => route.id);
			return fetchPrerenderViews(config, paths, routeInfo);
		},
		[client, config],
	);

	const handleNavigate = useCallback(
		async (target: NavigationTarget) => {
			const key = target.location.pathname + target.location.search;
			let result: NavigationViews | null = null;
			const cached = prefetches.current.get(key);
			if (cached) {
				prefetches.current.delete(key);
				if (Date.now() - cached.at < PREFETCH_TTL_MS) {
					try {
						result = await cached.promise;
					} catch {
						result = null;
					}
				}
			}
			if (result === null || result.status === "error") {
				result = await requestViews(target, false);
			}
			if (result.status === "redirect") {
				if (inBrowser) {
					window.location.assign(result.redirect || "/");
				}
				return;
			}
			if (result.status === "notFound") {
				if (inBrowser) {
					window.location.assign(result.redirect || "/not-found");
				}
				return;
			}
			if (result.status === "error" || !result.views) {
				throw new Error("Navigation failed on the server");
			}
			const { views, directives } = result;
			return () => {
				setCurrent((previous) => ({
					views: mergeNavigationViews(previous.views, views),
					directives: directives ?? previous.directives,
				}));
			};
		},
		[requestViews],
	);

	const handlePrefetch = useCallback(
		(target: NavigationTarget) => {
			if (!client.isConnected()) {
				return;
			}
			const key = target.location.pathname + target.location.search;
			const existing = prefetches.current.get(key);
			if (existing && Date.now() - existing.at < PREFETCH_TTL_MS) {
				return;
			}
			const routeInfo = buildRouteInfo(
				target.location,
				target.match.params,
				target.match.catchall,
			);
			const promise = client.navigateViews(routeInfo, { prefetch: true });
			promise.catch(() => {
				prefetches.current.delete(key);
			});
			prefetches.current.set(key, { at: Date.now(), promise });
		},
		[client],
	);

	return (
		<PulseRouterProvider
			routes={routes}
			routeLoaders={routeLoaders}
			initialUrl={url}
			onNavigate={handleNavigate}
			onPrefetch={handlePrefetch}
		>
			<PulseFrameworkNavigationBinder client={client} />
			<PulseProvider client={client} prerender={current}>
				<PulseRoutes />
			</PulseProvider>
		</PulseRouterProvider>
	);
}
