/**
 * Route matching utilities for Pulse router.
 */

export interface MatchResult {
	matched: boolean;
	params: Record<string, string>;
}

/**
 * Match a path pattern against an actual path.
 * Supports static paths and dynamic params (e.g., :id).
 *
 * @param pattern - The route pattern (e.g., '/users/:id')
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

	// Must have same number of segments for required params
	if (patternSegments.length !== pathSegments.length) {
		return { matched: false, params: {} };
	}

	const params: Record<string, string> = {};

	for (let i = 0; i < patternSegments.length; i++) {
		const patternSeg = patternSegments[i];
		const pathSeg = pathSegments[i];

		if (patternSeg.startsWith(":")) {
			// Dynamic param - extract name and value
			const paramName = patternSeg.slice(1);
			params[paramName] = pathSeg;
		} else if (patternSeg !== pathSeg) {
			// Static segment mismatch
			return { matched: false, params: {} };
		}
	}

	return { matched: true, params };
}
