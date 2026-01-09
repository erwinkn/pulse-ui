/**
 * Route matching utilities for Pulse router.
 */

export interface MatchResult {
	matched: boolean;
	params: Record<string, string | undefined | string[]>;
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
