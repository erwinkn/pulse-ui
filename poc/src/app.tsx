import { useCallback, useState } from "react";
import { getLoadedRegistry, loadRouteChunk } from "./router/loader";
import { createHoverPrefetch } from "./router/prefetch";
import { type ComponentRegistry, renderVdom, type VdomNode } from "./vdom-renderer";

/** Hardcoded VDOM for each route (real Pulse gets from Python) */
const routeVdom: Record<string, VdomNode> = {
	"/": {
		type: "HomeWidget",
		props: {},
		children: [],
	},
	"/dashboard": {
		type: "DashboardChart",
		props: {},
		children: [],
	},
	"/settings": {
		type: "SettingsForm",
		props: {},
		children: [],
	},
};

interface AppProps {
	initialVdom: VdomNode;
	initialRegistry: ComponentRegistry;
}

export function App({ initialVdom, initialRegistry }: AppProps) {
	const [vdom, setVdom] = useState<VdomNode>(initialVdom);
	const [registry, setRegistry] = useState<ComponentRegistry>(initialRegistry);
	const [loading, setLoading] = useState(false);

	const navigate = useCallback(async (path: string) => {
		setLoading(true);
		try {
			await loadRouteChunk(path);
			const newRegistry = getLoadedRegistry();
			const newVdom = routeVdom[path] ?? null;

			setRegistry(newRegistry);
			setVdom(newVdom);
			window.history.pushState({}, "", path);
		} finally {
			setLoading(false);
		}
	}, []);

	const handleNavClick = useCallback(
		(e: React.MouseEvent<HTMLAnchorElement>, path: string) => {
			e.preventDefault();
			navigate(path);
		},
		[navigate],
	);

	return (
		<div className="app">
			<nav>
				<a href="/" onClick={(e) => handleNavClick(e, "/")} {...createHoverPrefetch("/")}>
					Home
				</a>
				<a
					href="/dashboard"
					onClick={(e) => handleNavClick(e, "/dashboard")}
					{...createHoverPrefetch("/dashboard")}
				>
					Dashboard
				</a>
				<a
					href="/settings"
					onClick={(e) => handleNavClick(e, "/settings")}
					{...createHoverPrefetch("/settings")}
				>
					Settings
				</a>
			</nav>

			{loading ? (
				<div className="loading">Loading...</div>
			) : (
				<main>{renderVdom(vdom, registry)}</main>
			)}
		</div>
	);
}

/** Get VDOM for a given path (exported for client entry) */
export function getVdomForPath(path: string): VdomNode {
	return routeVdom[path] ?? null;
}
