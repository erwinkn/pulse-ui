/**
 * Route matching utilities for Pulse router.
 */

export interface MatchResult {
	matched: boolean;
	params: Record<string, string | undefined>;
}

/**
 * Match a path pattern against an actual path.
 * Supports static paths, dynamic params (e.g., :id), and optional params (e.g., :id?).
 *
 * @param pattern - The route pattern (e.g., '/users/:id?')
 * @param path - The actual path to match (e.g., '/users/123')
 * @returns MatchResult indicating if matched and extracted params
 */
export function matchPath(pattern: string, path: string): MatchResult {
	// Normalize paths by removing trailing slashes (except root)
	const normalizedPattern = pattern === "/" ? "/" : pattern.replace(/\/$/, "");
	const normalizedPath = path === "/" ? "/" : path.replace(/\/$/, "");

	// Split into segments
	const patternSegments = normalizedPattern.split("/").filter(Boolean);
	const pathSegments = normalizedPath.split("/").filter(Boolean);

	// Count required segments (non-optional)
	const requiredCount = patternSegments.filter((seg) => !seg.endsWith("?")).length;

	// Path must have at least required segments, at most all pattern segments
	if (pathSegments.length < requiredCount || pathSegments.length > patternSegments.length) {
		return { matched: false, params: {} };
	}

	const params: Record<string, string | undefined> = {};

	for (let i = 0; i < patternSegments.length; i++) {
		const patternSeg = patternSegments[i];
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

	return { matched: true, params };
}
