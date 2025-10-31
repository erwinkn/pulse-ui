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
import { type Directives, PulseSocketIOClient } from "./client";
import type { RouteInfo } from "./helpers";
import type { ServerErrorInfo } from "./messages";
import { VDOMRenderer } from "./renderer";
import type { ComponentRegistry, VDOM } from "./vdom";

// =================================================================
// Types
// =================================================================

export interface PulseConfig {
	serverAddress: string;
}

export type PulsePrerenderView = {
	vdom: VDOM;
	callbacks: string[];
	render_props: string[];
	css_refs: string[];
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
	const [connected, setConnected] = useState(true);
	const rrNavigate = useNavigate();
	const { directives } = prerender;

	// biome-ignore lint/correctness/useExhaustiveDependencies: another useEffect syncs the directives without recreating the client
	const client = useMemo(() => {
		return new PulseSocketIOClient(config.serverAddress, directives, rrNavigate);
	}, [config.serverAddress, rrNavigate]);
	useEffect(() => client.setDirectives(directives), [client, directives]);
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
	cssModules: Record<string, Record<string, string>>;
}

export function PulseView({ externalComponents, path, cssModules }: PulseViewProps) {
	const client = usePulseClient();
	const initialView = usePulsePrerender(path);
	// biome-ignore lint/correctness/useExhaustiveDependencies: We only want to lose the renderer on unmount. initialView will change on every navigation with our current setup, so we hack around it with another useEffect below. This is not ideal and will be fixed in the future.
	const renderer = useMemo(
		() =>
			new VDOMRenderer(
				client,
				path,
				externalComponents,
				cssModules,
				initialView.callbacks,
				initialView.render_props,
				initialView.css_refs,
			),
		[client, path, externalComponents, cssModules],
	);
	const [tree, setTree] = useState<ReactNode>(() => renderer.init(initialView));
	const [serverError, setServerError] = useState<ServerErrorInfo | null>(null);

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

	// biome-ignore lint/correctness/useExhaustiveDependencies: We don't want to unmount on navigation, so another useEffect sync the routeInfo on navigation.
	useEffect(() => {
		if (inBrowser) {
			client.mountView(path, {
				routeInfo,
				onInit: (view) => {
					setTree(renderer.init(view));
				},
				onUpdate: (ops) => {
					setTree((prev) => (prev == null ? prev : renderer.applyUpdates(prev, ops)));
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
		//  routeInfo is NOT included here on purpose
	}, [client, renderer, path]);

	useEffect(() => {
		if (inBrowser) {
			client.navigate(path, routeInfo);
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
