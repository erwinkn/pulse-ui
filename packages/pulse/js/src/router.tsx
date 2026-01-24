import type { ComponentType, MouseEvent, ReactNode } from "react";
import {
	createContext,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import type { LocationLike, RouteInfo } from "./helpers";
import { buildRouteInfo } from "./helpers";

export type PulseRoute = {
	id: string;
	path?: string;
	index?: boolean;
	file: string;
	children?: PulseRoute[];
};

export type RouteModule = {
	default: ComponentType<any>;
	registry?: Record<string, unknown>;
	path?: string;
};

export type RouteLoader = () => Promise<RouteModule>;
export type RouteLoaderMap = Record<string, RouteLoader>;

export type NavigateOptions = {
	replace?: boolean;
};

export type NavigateFunction = (to: string, options?: NavigateOptions) => void;

export type MatchResult = {
	matches: PulseRoute[];
	params: Record<string, string | undefined>;
	catchall: string[];
};

type RouterState = {
	location: LocationLike;
	matches: PulseRoute[];
	params: Record<string, string | undefined>;
	catchall: string[];
	navigate: NavigateFunction;
	prefetch: (to: string) => void;
	isNavigating: boolean;
	routeInfo: RouteInfo;
};

const RouterContext = createContext<RouterState | null>(null);
const OutletIndexContext = createContext(0);

const inBrowser = typeof window !== "undefined";

const routeModuleCache = new Map<string, RouteModule>();

type RouteSegment = {
	name: string;
	dynamic: boolean;
	optional: boolean;
	splat: boolean;
};

function normalizePathname(pathname: string): string {
	if (!pathname.startsWith("/")) {
		pathname = `/${pathname}`;
	}
	if (pathname.length > 1 && pathname.endsWith("/")) {
		return pathname.slice(0, -1);
	}
	return pathname;
}

function splitPathname(pathname: string): string[] {
	const normalized = normalizePathname(pathname);
	const stripped = normalized.replace(/^\/+|\/+$/g, "");
	return stripped.length ? stripped.split("/") : [];
}

function parseRoutePath(path: string | undefined): RouteSegment[] {
	if (!path) {
		return [];
	}
	const trimmed = path.replace(/^\/+|\/+$/g, "");
	if (!trimmed) {
		return [];
	}
	return trimmed.split("/").map((part) => {
		const optional = part.endsWith("?");
		const raw = optional ? part.slice(0, -1) : part;
		const splat = raw === "*";
		const dynamic = raw.startsWith(":");
		const name = dynamic ? raw.slice(1) : raw;
		return { name, dynamic, optional, splat };
	});
}

type SegmentMatch = {
	consumed: number;
	params: Record<string, string | undefined>;
	catchall: string[];
	score: number;
};

function matchSegments(
	routeSegments: RouteSegment[],
	pathSegments: string[],
	index = 0,
): SegmentMatch[] {
	if (index >= routeSegments.length) {
		return [
			{
				consumed: 0,
				params: {},
				catchall: [],
				score: 0,
			},
		];
	}

	const segment = routeSegments[index]!;

	if (segment.splat) {
		return [
			{
				consumed: pathSegments.length,
				params: {},
				catchall: pathSegments.slice(),
				score: 0,
			},
		];
	}

	const results: SegmentMatch[] = [];
	const head = pathSegments[0];

	if (head !== undefined) {
		if (segment.dynamic) {
			for (const next of matchSegments(routeSegments, pathSegments.slice(1), index + 1)) {
				results.push({
					consumed: 1 + next.consumed,
					params: { ...next.params, [segment.name]: head },
					catchall: next.catchall,
					score: 2 + next.score,
				});
			}
		} else if (segment.name === head) {
			for (const next of matchSegments(routeSegments, pathSegments.slice(1), index + 1)) {
				results.push({
					consumed: 1 + next.consumed,
					params: { ...next.params },
					catchall: next.catchall,
					score: 3 + next.score,
				});
			}
		}
	}

	if (segment.optional) {
		for (const next of matchSegments(routeSegments, pathSegments, index + 1)) {
			results.push({
				consumed: next.consumed,
				params: { ...next.params },
				catchall: next.catchall,
				score: next.score,
			});
		}
	}

	return results;
}

type MatchCandidate = {
	matches: PulseRoute[];
	params: Record<string, string | undefined>;
	catchall: string[];
	remaining: string[];
	score: number;
};

function matchBranch(
	routes: PulseRoute[],
	pathSegments: string[],
	parentMatches: PulseRoute[] = [],
	parentParams: Record<string, string | undefined> = {},
	parentCatchall: string[] = [],
	parentScore = 0,
): MatchCandidate[] {
	const results: MatchCandidate[] = [];

	for (const route of routes) {
		const isLayout = route.path == null && !route.index;
		if (isLayout) {
			if (!route.children || route.children.length === 0) {
				continue;
			}
			for (const child of matchBranch(
				route.children,
				pathSegments,
				[...parentMatches, route],
				parentParams,
				parentCatchall,
				parentScore,
			)) {
				results.push(child);
			}
			continue;
		}

		if (route.index || route.path === "") {
			if (pathSegments.length === 0) {
				results.push({
					matches: [...parentMatches, route],
					params: { ...parentParams },
					catchall: parentCatchall.slice(),
					remaining: [],
					score: parentScore + 4,
				});
			}
			continue;
		}

		const segments = parseRoutePath(route.path);
		const matches = matchSegments(segments, pathSegments);

		for (const match of matches) {
			const remaining = pathSegments.slice(match.consumed);
			const nextParams = { ...parentParams, ...match.params };
			const nextCatchall = match.catchall.length > 0 ? match.catchall : parentCatchall;
			const nextScore = parentScore + match.score;
			const nextMatches = [...parentMatches, route];

			if (route.children && route.children.length > 0) {
				const childMatches = matchBranch(
					route.children,
					remaining,
					nextMatches,
					nextParams,
					nextCatchall,
					nextScore,
				);
				if (childMatches.length > 0) {
					results.push(...childMatches);
					continue;
				}
			}

			if (remaining.length === 0) {
				results.push({
					matches: nextMatches,
					params: nextParams,
					catchall: nextCatchall,
					remaining: [],
					score: nextScore,
				});
			}
		}
	}

	return results;
}

function pickBestMatch(candidates: MatchCandidate[]): MatchCandidate | null {
	if (candidates.length === 0) {
		return null;
	}
	let best = candidates[0]!;
	for (const candidate of candidates.slice(1)) {
		if (candidate.score > best.score) {
			best = candidate;
			continue;
		}
		if (candidate.score === best.score && candidate.matches.length > best.matches.length) {
			best = candidate;
		}
	}
	return best;
}

export function matchRoutes(routes: PulseRoute[], pathname: string): MatchResult | null {
	const segments = splitPathname(pathname);
	const candidates = matchBranch(routes, segments);
	const best = pickBestMatch(candidates);
	if (!best || best.remaining.length > 0) {
		return null;
	}
	return {
		matches: best.matches,
		params: best.params,
		catchall: best.catchall,
	};
}

export async function loadRouteModule(
	id: string,
	loaders: RouteLoaderMap,
): Promise<RouteModule> {
	const cached = routeModuleCache.get(id);
	if (cached) {
		return cached;
	}
	const loader = loaders[id];
	if (!loader) {
		throw new Error(`No route loader registered for ${id}`);
	}
	const mod = await loader();
	routeModuleCache.set(id, mod);
	return mod;
}

export async function preloadRoutesForPath(
	routes: PulseRoute[],
	loaders: RouteLoaderMap,
	pathname: string,
): Promise<void> {
	const match = matchRoutes(routes, pathname);
	if (!match) {
		return;
	}
	await Promise.all(match.matches.map((route) => loadRouteModule(route.id, loaders)));
}

export function prefetchRouteModules(
	routes: PulseRoute[],
	loaders: RouteLoaderMap,
	pathname: string,
): void {
	const match = matchRoutes(routes, pathname);
	if (!match) {
		return;
	}
	for (const route of match.matches) {
		void loadRouteModule(route.id, loaders);
	}
}

export function useLocation(): LocationLike {
	const ctx = useRouter();
	return ctx.location;
}

export function useNavigate(): NavigateFunction {
	const ctx = useRouter();
	return ctx.navigate;
}

export function useParams(): Record<string, string | undefined> {
	const ctx = useRouter();
	return ctx.params;
}

export function useRouteInfo(): RouteInfo {
	const ctx = useRouter();
	return ctx.routeInfo;
}

export function useRouter(): RouterState {
	const ctx = useContext(RouterContext);
	if (!ctx) {
		throw new Error("Pulse router is not available");
	}
	return ctx;
}

function resolveHref(to: string, basePathname: string): string {
	if (to.startsWith("/")) {
		return normalizePathname(to);
	}
	if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(to)) {
		return to;
	}
	const base = basePathname.endsWith("/") ? basePathname : `${basePathname}/`;
	const url = new URL(to, `http://pulse${base}`);
	return normalizePathname(url.pathname) + url.search + url.hash;
}

type NavigateTarget = {
	location: LocationLike;
	match: MatchResult;
};

export function PulseRouterProvider({
	routes,
	routeLoaders,
	initialUrl,
	onNavigate,
	children,
}: {
	routes: PulseRoute[];
	routeLoaders: RouteLoaderMap;
	initialUrl?: string;
	onNavigate?: (target: NavigateTarget) => Promise<void>;
	children: ReactNode;
}) {
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
			return {
				pathname: normalizePathname(window.location.pathname),
				search: window.location.search,
				hash: window.location.hash,
			};
		}
		return { pathname: "/", search: "", hash: "" };
	}, [initialUrl]);

	const initialMatch = useMemo(() => matchRoutes(routes, initialLocation.pathname), [
		initialLocation.pathname,
		routes,
	]);

	const [location, setLocation] = useState<LocationLike>(initialLocation);
	const [matchState, setMatchState] = useState<MatchResult | null>(initialMatch);
	const [isNavigating, setIsNavigating] = useState(false);
	const latestLocationRef = useRef<LocationLike>(initialLocation);

	const applyNavigation = useCallback(
		async (nextLocation: LocationLike, options: NavigateOptions & { pop?: boolean } = {}) => {
			const match = matchRoutes(routes, nextLocation.pathname);
			if (!match) {
				if (inBrowser && !options.pop) {
					window.location.assign(
						`${nextLocation.pathname}${nextLocation.search}${nextLocation.hash}`,
					);
				}
				return;
			}

			setIsNavigating(true);
			try {
				await preloadRoutesForPath(routes, routeLoaders, nextLocation.pathname);
				if (onNavigate) {
					await onNavigate({ location: nextLocation, match });
				}
				if (inBrowser && !options.pop) {
					const url = `${nextLocation.pathname}${nextLocation.search}${nextLocation.hash}`;
					if (options.replace) {
						window.history.replaceState({}, "", url);
					} else {
						window.history.pushState({}, "", url);
					}
				}
				latestLocationRef.current = nextLocation;
				setLocation(nextLocation);
				setMatchState(match);
			} finally {
				setIsNavigating(false);
			}
		},
		[onNavigate, routeLoaders, routes],
	);

	const navigate = useCallback<NavigateFunction>(
		(to, options = {}) => {
			const href = resolveHref(to, latestLocationRef.current.pathname);
			if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href)) {
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
			if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href)) {
				return;
			}
			const url = new URL(href, "http://pulse");
			prefetchRouteModules(routes, routeLoaders, url.pathname);
		},
		[routeLoaders, routes],
	);

	useEffect(() => {
		if (!inBrowser) {
			return;
		}
		const onPop = () => {
			const nextLocation = {
				pathname: normalizePathname(window.location.pathname),
				search: window.location.search,
				hash: window.location.hash,
			};
			void applyNavigation(nextLocation, { pop: true, replace: true });
		};
		window.addEventListener("popstate", onPop);
		return () => window.removeEventListener("popstate", onPop);
	}, [applyNavigation]);

	useEffect(() => {
		if (!inBrowser) {
			return;
		}
		void preloadRoutesForPath(routes, routeLoaders, location.pathname);
	}, [location.pathname, routeLoaders, routes]);

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
			routeInfo,
		};
	}, [location, matchState, navigate, prefetch, isNavigating, routeInfo]);

	return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function PulseRoutes({ fallback }: { fallback?: ReactNode }) {
	const { matches, isNavigating } = useRouter();
	if (matches.length === 0) {
		return null;
	}
	const mod = routeModuleCache.get(matches[0]!.id);
	if (!mod) {
		return isNavigating ? fallback ?? null : null;
	}
	const Component = mod.default;
	return (
		<OutletIndexContext.Provider value={1}>
			<Component />
		</OutletIndexContext.Provider>
	);
}

export function Outlet() {
	const { matches } = useRouter();
	const index = useContext(OutletIndexContext);
	const match = matches[index];
	if (!match) {
		return null;
	}
	const mod = routeModuleCache.get(match.id);
	if (!mod) {
		return null;
	}
	const Component = mod.default;
	return (
		<OutletIndexContext.Provider value={index + 1}>
			<Component />
		</OutletIndexContext.Provider>
	);
}

export type LinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
	to: string;
	prefetch?: "none" | "intent" | "render" | "viewport";
	reloadDocument?: boolean;
	replace?: boolean;
};

export function Link({
	to,
	prefetch = "intent",
	reloadDocument,
	replace,
	onClick,
	...rest
}: LinkProps) {
	const navigate = useNavigate();
	const { prefetch: prefetchRoute } = useRouter();
	const ref = useRef<HTMLAnchorElement | null>(null);

	useEffect(() => {
		if (prefetch === "render") {
			prefetchRoute(to);
		}
	}, [prefetch, prefetchRoute, to]);

	useEffect(() => {
		if (prefetch !== "viewport") {
			return;
		}
		const el = ref.current;
		if (!el || !("IntersectionObserver" in window)) {
			return;
		}
		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						prefetchRoute(to);
						observer.disconnect();
						break;
					}
				}
			},
			{ rootMargin: "50px" },
		);
		observer.observe(el);
		return () => observer.disconnect();
	}, [prefetch, prefetchRoute, to]);

	const handleClick = useCallback(
		(event: MouseEvent<HTMLAnchorElement>) => {
			if (onClick) {
				onClick(event);
			}
			if (
				event.defaultPrevented ||
				event.button !== 0 ||
				event.metaKey ||
				event.altKey ||
				event.ctrlKey ||
				event.shiftKey
			) {
				return;
			}
			if (reloadDocument) {
				return;
			}
			event.preventDefault();
			navigate(to, { replace });
		},
		[navigate, onClick, reloadDocument, replace, to],
	);

	const handleMouseEnter = useCallback(() => {
		if (prefetch === "intent") {
			prefetchRoute(to);
		}
	}, [prefetch, prefetchRoute, to]);

	return (
		<a
			{...rest}
			ref={ref}
			href={to}
			onClick={handleClick}
			onMouseEnter={handleMouseEnter}
		/>
	);
}
