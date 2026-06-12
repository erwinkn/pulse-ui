import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
	useSyncExternalStore,
} from "react";
import { buildRouteInfo, type LocationLike, type RouteInfo } from "../helpers";
import { matchRoutes, type MatchResult, normalizePathname, type PulseRoute } from "./match";
import {
	getRouteModule,
	getRouteModulesVersion,
	loadRouteModule,
	preloadRoutesForPath,
	prefetchRouteModules,
	type RouteLoaderMap,
	subscribeRouteModules,
} from "./modules";

export type NavigateOptions = {
	replace?: boolean;
	preventScrollReset?: boolean;
};

export type NavigateFunction = (to: string | number, options?: NavigateOptions) => void;

export type NavigationTarget = {
	location: LocationLike;
	match: MatchResult;
};

export type NavigationError = {
	error: Error;
	location: LocationLike;
};

type RouterState = {
	location: LocationLike;
	matches: PulseRoute[];
	params: Record<string, string | undefined>;
	catchall: string[];
	routeInfo: RouteInfo;
	navigate: NavigateFunction;
	prefetch: (to: string) => void;
	isNavigating: boolean;
	navigationError: NavigationError | null;
	routes: PulseRoute[];
	routeLoaders: RouteLoaderMap;
};

const RouterContext = createContext<RouterState | null>(null);
const OutletIndexContext = createContext(0);

const inBrowser = typeof window !== "undefined";

function isExternalHref(href: string): boolean {
	// Protocol-relative URLs (//host/...) and explicit schemes are external.
	return href.startsWith("//") || /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href);
}

export function resolveHref(to: string, basePathname: string): string {
	if (isExternalHref(to)) {
		return to;
	}
	if (to.startsWith("/")) {
		const url = new URL(to, "http://pulse");
		return normalizePathname(url.pathname) + url.search + url.hash;
	}
	const base = basePathname.endsWith("/") ? basePathname : `${basePathname}/`;
	const url = new URL(to, `http://pulse${base}`);
	return normalizePathname(url.pathname) + url.search + url.hash;
}

function currentWindowLocation(): LocationLike {
	return {
		pathname: normalizePathname(window.location.pathname),
		search: window.location.search,
		hash: window.location.hash,
	};
}

function locationToUrl(location: LocationLike): string {
	return `${location.pathname}${location.search}${location.hash}`;
}

// ---------------------------------------------------------------------------
// Scroll restoration
//
// Each history entry gets a key stored in history.state; scroll positions are
// remembered per key so back/forward restores them even when two entries share
// a pathname.
// ---------------------------------------------------------------------------

const scrollPositions = new Map<string, { x: number; y: number }>();
let nextHistoryKey = 0;

function readHistoryKey(): string {
	const state = window.history.state;
	if (state && typeof state.__pulseKey === "string") {
		return state.__pulseKey;
	}
	return "initial";
}

function newHistoryKey(): string {
	nextHistoryKey += 1;
	return `p${nextHistoryKey}-${Date.now().toString(36)}`;
}

export function scrollToHash(hash: string): void {
	const id = hash.startsWith("#") ? hash.slice(1) : hash;
	if (!id) return;
	const element = document.getElementById(id);
	if (element) {
		element.scrollIntoView();
	}
}

export interface PulseRouterProviderProps {
	routes: PulseRoute[];
	routeLoaders: RouteLoaderMap;
	/** URL of the initial request; required for SSR, optional in the browser. */
	initialUrl?: string;
	/**
	 * Called before a navigation commits. Typically fetches the new views from
	 * the Pulse server. Throwing aborts the navigation with an error; returning
	 * false abandons it silently (e.g. a redirect took over). May return a
	 * callback, which runs in the same render batch as the location commit so
	 * view data and route state swap atomically.
	 */
	onNavigate?: (target: NavigationTarget) => Promise<void | false | (() => void)>;
	/** Called when a link wants to prefetch a target URL. */
	onPrefetch?: (target: NavigationTarget) => void;
	children: ReactNode;
}

export function PulseRouterProvider({
	routes,
	routeLoaders,
	initialUrl,
	onNavigate,
	onPrefetch,
	children,
}: PulseRouterProviderProps) {
	const initialLocation = useMemo<LocationLike>(() => {
		if (initialUrl) {
			const url = new URL(initialUrl, "http://pulse");
			return {
				pathname: normalizePathname(url.pathname),
				search: url.search,
				hash: url.hash,
			};
		}
		if (inBrowser) {
			return currentWindowLocation();
		}
		return { pathname: "/", search: "", hash: "" };
	}, [initialUrl]);

	const initialMatch = useMemo(
		() => matchRoutes(routes, initialLocation.pathname),
		[initialLocation.pathname, routes],
	);

	const [location, setLocation] = useState<LocationLike>(initialLocation);
	const [matchState, setMatchState] = useState<MatchResult | null>(initialMatch);
	const [isNavigating, setIsNavigating] = useState(false);
	const [navigationError, setNavigationError] = useState<NavigationError | null>(null);
	const latestLocationRef = useRef<LocationLike>(initialLocation);
	const navSeqRef = useRef(0);
	// Key of the history entry currently displayed; scroll positions are saved
	// under it whenever we navigate away (including pops).
	const historyKeyRef = useRef<string>(inBrowser ? readHistoryKey() : "initial");

	useEffect(() => {
		if (!inBrowser) return;
		window.history.scrollRestoration = "manual";
	}, []);

	const applyNavigation = useCallback(
		async (
			nextLocation: LocationLike,
			options: NavigateOptions & { pop?: boolean; onError?: (error: Error) => void } = {},
		) => {
			const seq = ++navSeqRef.current;
			const match = matchRoutes(routes, nextLocation.pathname);
			if (!match) {
				// Unknown route: let the server handle it with a full document load.
				// On popstate the URL has already changed, so a reload resyncs both.
				if (inBrowser) {
					if (options.pop) {
						window.location.reload();
					} else {
						window.location.assign(locationToUrl(nextLocation));
					}
				}
				return;
			}

			// Same-pathname navigations (query/hash changes) cannot change the
			// matched views; commit directly and let mounted views sync their
			// route info over the socket.
			const samePath = nextLocation.pathname === latestLocationRef.current.pathname;

			setIsNavigating(true);
			try {
				let commit: void | false | (() => void) = undefined;
				if (!samePath) {
					await preloadRoutesForPath(routes, routeLoaders, nextLocation.pathname);
					if (onNavigate) {
						commit = await onNavigate({ location: nextLocation, match });
					}
				}
				if (seq !== navSeqRef.current) {
					// Superseded by a newer navigation; drop this one.
					return;
				}
				if (commit === false) {
					// Abandoned (e.g. the server redirected and a document
					// navigation is in flight); leave router state untouched.
					return;
				}
				if (commit) {
					commit();
				}
				let popKey: string | null = null;
				if (inBrowser) {
					// Remember the scroll position of the entry we are leaving.
					scrollPositions.set(historyKeyRef.current, {
						x: window.scrollX,
						y: window.scrollY,
					});
					if (options.pop) {
						popKey = readHistoryKey();
						historyKeyRef.current = popKey;
					} else {
						const url = locationToUrl(nextLocation);
						const key = newHistoryKey();
						const state = { __pulseKey: key };
						if (options.replace) {
							window.history.replaceState(state, "", url);
						} else {
							window.history.pushState(state, "", url);
						}
						historyKeyRef.current = key;
					}
				}
				latestLocationRef.current = nextLocation;
				setLocation(nextLocation);
				setMatchState(match);
				setNavigationError(null);
				if (inBrowser && !options.preventScrollReset) {
					requestAnimationFrame(() => {
						if (seq !== navSeqRef.current) return;
						if (popKey !== null) {
							const saved = scrollPositions.get(popKey);
							window.scrollTo(saved?.x ?? 0, saved?.y ?? 0);
						} else if (nextLocation.hash) {
							scrollToHash(nextLocation.hash);
						} else {
							window.scrollTo(0, 0);
						}
					});
				}
			} catch (rawError) {
				if (seq !== navSeqRef.current) {
					return;
				}
				const error = rawError instanceof Error ? rawError : new Error(String(rawError));
				console.error("[Pulse] Navigation failed:", error);
				options.onError?.(error);
				if (options.pop && inBrowser) {
					// The browser URL already moved; reload to resync.
					window.location.reload();
					return;
				}
				setNavigationError({ error, location: nextLocation });
			} finally {
				if (seq === navSeqRef.current) {
					setIsNavigating(false);
				}
			}
		},
		[onNavigate, routeLoaders, routes],
	);

	const navigate = useCallback<NavigateFunction>(
		(to, options = {}) => {
			if (typeof to === "number") {
				if (inBrowser) {
					window.history.go(to);
				}
				return;
			}
			const href = resolveHref(to, latestLocationRef.current.pathname);
			if (isExternalHref(href)) {
				if (inBrowser) {
					if (options.replace) {
						window.location.replace(href);
					} else {
						window.location.assign(href);
					}
				}
				return;
			}
			const url = new URL(href, "http://pulse");
			void applyNavigation(
				{
					pathname: normalizePathname(url.pathname),
					search: url.search,
					hash: url.hash,
				},
				options,
			);
		},
		[applyNavigation],
	);

	const prefetch = useCallback(
		(to: string) => {
			const href = resolveHref(to, latestLocationRef.current.pathname);
			if (isExternalHref(href)) {
				return;
			}
			const url = new URL(href, "http://pulse");
			const pathname = normalizePathname(url.pathname);
			prefetchRouteModules(routes, routeLoaders, pathname);
			if (onPrefetch) {
				const match = matchRoutes(routes, pathname);
				if (match) {
					onPrefetch({
						location: { pathname, search: url.search, hash: url.hash },
						match,
					});
				}
			}
		},
		[onPrefetch, routeLoaders, routes],
	);

	useEffect(() => {
		if (!inBrowser) {
			return;
		}
		const onPop = () => {
			void applyNavigation(currentWindowLocation(), { pop: true });
		};
		window.addEventListener("popstate", onPop);
		return () => window.removeEventListener("popstate", onPop);
	}, [applyNavigation]);

	const routeInfo = useMemo(() => {
		if (!matchState) {
			return buildRouteInfo(location, {}, []);
		}
		return buildRouteInfo(location, matchState.params, matchState.catchall);
	}, [location, matchState]);

	const value = useMemo<RouterState>(() => {
		return {
			location,
			matches: matchState?.matches ?? [],
			params: matchState?.params ?? {},
			catchall: matchState?.catchall ?? [],
			navigate,
			prefetch,
			isNavigating,
			navigationError,
			routeInfo,
			routes,
			routeLoaders,
		};
	}, [
		location,
		matchState,
		navigate,
		prefetch,
		isNavigating,
		navigationError,
		routeInfo,
		routes,
		routeLoaders,
	]);

	return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter(): RouterState {
	const ctx = useContext(RouterContext);
	if (!ctx) {
		throw new Error("Pulse router is not available");
	}
	return ctx;
}

export function useLocation(): LocationLike {
	return useRouter().location;
}

export function useNavigate(): NavigateFunction {
	return useRouter().navigate;
}

export function useParams(): Record<string, string | undefined> {
	return useRouter().params;
}

export function useRouteInfo(): RouteInfo {
	return useRouter().routeInfo;
}

export function useNavigationError(): NavigationError | null {
	return useRouter().navigationError;
}

function useRouteModulesVersion(): number {
	return useSyncExternalStore(
		subscribeRouteModules,
		getRouteModulesVersion,
		getRouteModulesVersion,
	);
}

function RouteMatch({ index }: { index: number }) {
	const { matches, routeLoaders } = useRouter();
	useRouteModulesVersion();
	const match = matches[index];

	useEffect(() => {
		if (match && !getRouteModule(match.id, routeLoaders)) {
			loadRouteModule(match.id, routeLoaders).catch((error) => {
				console.error(`[Pulse] Failed to load route module '${match.id}':`, error);
			});
		}
	}, [match, routeLoaders]);

	if (!match) {
		return null;
	}
	const mod = getRouteModule(match.id, routeLoaders);
	if (!mod) {
		// Module load is in flight; the version subscription re-renders us when
		// it lands.
		return null;
	}
	const Component = mod.default;
	return (
		<OutletIndexContext.Provider value={index + 1}>
			<Component />
		</OutletIndexContext.Provider>
	);
}

export function PulseRoutes() {
	return <RouteMatch index={0} />;
}

export function Outlet() {
	const index = useContext(OutletIndexContext);
	return <RouteMatch index={index} />;
}
