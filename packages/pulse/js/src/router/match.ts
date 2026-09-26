/**
 * Route matching for the Pulse router.
 *
 * Mirrors the Python matcher in `pulse/routing.py` (`match_route_tree`):
 * static segments score higher than dynamic (`:id`), dynamic higher than
 * optional (`:id?`), and catch-all (`*`) lowest. Layouts are pathless nodes
 * that never consume URL segments.
 */

export type PulseRoute = {
	id: string;
	path?: string;
	index?: boolean;
	children?: PulseRoute[];
};

export type MatchResult = {
	matches: PulseRoute[];
	params: Record<string, string | undefined>;
	catchall: string[];
};

type RouteSegment = {
	name: string;
	dynamic: boolean;
	optional: boolean;
	splat: boolean;
};

export function normalizePathname(pathname: string): string {
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
		return [{ consumed: 0, params: {}, catchall: [], score: 0 }];
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
			results.push(
				...matchBranch(
					route.children,
					pathSegments,
					[...parentMatches, route],
					parentParams,
					parentCatchall,
					parentScore,
				),
			);
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
		for (const match of matchSegments(segments, pathSegments)) {
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
