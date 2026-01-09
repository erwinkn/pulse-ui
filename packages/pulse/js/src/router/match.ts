/**
 * Route matching utilities for Pulse router.
 */

export interface MatchResult {
	matched: boolean;
	params: Record<string, string | undefined | string[]>;
}

/**
 * Segment specificity: static (3) > dynamic (2) > optional (1) > catch-all (0)
 */
function getSegmentSpecificity(segment: string): number {
	if (segment === "*") return 0;
	if (segment.startsWith(":") && segment.endsWith("?")) return 1;
	if (segment.startsWith(":")) return 2;
	return 3;
}

/**
 * Compare two route patterns by specificity.
 * Returns -1 if a is more specific, 1 if b is more specific, 0 if equal.
 *
 * Specificity rules (per segment):
 * - Static segments rank higher than dynamic
 * - Dynamic segments rank higher than optional
 * - Optional segments rank higher than catch-all
 *
 * @param a - First route pattern
 * @param b - Second route pattern
 * @returns -1 if a wins, 1 if b wins, 0 if equal
 */
export function compareRoutes(a: string, b: string): -1 | 0 | 1 {
	const normalizedA = a === "/" ? "/" : a.replace(/\/$/, "");
	const normalizedB = b === "/" ? "/" : b.replace(/\/$/, "");

	const segmentsA = normalizedA.split("/").filter(Boolean);
	const segmentsB = normalizedB.split("/").filter(Boolean);

	const maxLen = Math.max(segmentsA.length, segmentsB.length);

	for (let i = 0; i < maxLen; i++) {
		const segA = segmentsA[i];
		const segB = segmentsB[i];

		// If one pattern is shorter, the longer one wins at this position
		// (having a segment is more specific than not having one)
		if (segA === undefined && segB !== undefined) return 1;
		if (segA !== undefined && segB === undefined) return -1;

		const specA = getSegmentSpecificity(segA);
		const specB = getSegmentSpecificity(segB);

		if (specA > specB) return -1;
		if (specA < specB) return 1;
	}

	return 0;
}

export interface RouteMatch<T = unknown> {
	route: T;
	pattern: string;
	params: MatchResult["params"];
}

/**
 * Select the best matching route from a list of routes for a given path.
 * Returns the most specific match based on segment-by-segment comparison.
 *
 * @param routes - Array of objects with `pattern` property
 * @param path - The actual path to match
 * @returns The best match with params, or null if no match
 */
export function selectBestMatch<T extends { pattern: string }>(
	routes: T[],
	path: string,
): RouteMatch<T> | null {
	let bestMatch: RouteMatch<T> | null = null;

	for (const route of routes) {
		const result = matchPath(route.pattern, path);
		if (!result.matched) continue;

		if (bestMatch === null || compareRoutes(route.pattern, bestMatch.pattern) < 0) {
			bestMatch = { route, pattern: route.pattern, params: result.params };
		}
	}

	return bestMatch;
}

/**
 * Match a path pattern against an actual path.
 * Supports static paths, dynamic params (e.g., :id), optional params (e.g., :id?),
 * and catch-all (*) for matching remaining segments.
 *
 * @param pattern - The route pattern (e.g., '/files/*')
 * @param path - The actual path to match (e.g., '/files/a/b/c')
 * @returns MatchResult indicating if matched and extracted params
 */
export function matchPath(pattern: string, path: string): MatchResult {
	// Normalize paths by removing trailing slashes (except root)
	const normalizedPattern = pattern === "/" ? "/" : pattern.replace(/\/$/, "");
	const normalizedPath = path === "/" ? "/" : path.replace(/\/$/, "");

	// Split into segments
	const patternSegments = normalizedPattern.split("/").filter(Boolean);
	const pathSegments = normalizedPath.split("/").filter(Boolean);

	// Check for catch-all (*) - must be last segment
	const catchAllIndex = patternSegments.indexOf("*");
	const hasCatchAll = catchAllIndex !== -1;

	if (hasCatchAll && catchAllIndex !== patternSegments.length - 1) {
		// Catch-all must be last segment
		return { matched: false, params: {} };
	}

	// Segments before catch-all (or all segments if no catch-all)
	const prefixSegments = hasCatchAll ? patternSegments.slice(0, -1) : patternSegments;

	// Count required segments (non-optional, excluding catch-all)
	const requiredCount = prefixSegments.filter((seg) => !seg.endsWith("?")).length;

	// Path must have at least required segments
	// Without catch-all: also at most all pattern segments
	if (pathSegments.length < requiredCount) {
		return { matched: false, params: {} };
	}
	if (!hasCatchAll && pathSegments.length > patternSegments.length) {
		return { matched: false, params: {} };
	}

	const params: Record<string, string | undefined | string[]> = {};

	for (let i = 0; i < prefixSegments.length; i++) {
		const patternSeg = prefixSegments[i];
		const pathSeg = pathSegments[i];
		const isOptional = patternSeg.endsWith("?");

		if (patternSeg.startsWith(":")) {
			// Dynamic param - extract name (strip : and optional ?)
			const paramName = isOptional ? patternSeg.slice(1, -1) : patternSeg.slice(1);
			params[paramName] = pathSeg; // undefined if pathSeg doesn't exist
		} else if (pathSeg !== undefined && patternSeg !== pathSeg) {
			// Static segment mismatch
			return { matched: false, params: {} };
		} else if (pathSeg === undefined && !isOptional) {
			// Missing required static segment
			return { matched: false, params: {} };
		}
	}

	// Handle catch-all: capture remaining segments as array
	if (hasCatchAll) {
		params["*"] = pathSegments.slice(prefixSegments.length);
	}

	return { matched: true, params };
}
