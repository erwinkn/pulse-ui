/**
 * Route matching utilities for Pulse router.
 */

export interface MatchResult {
	matched: boolean;
	params: Record<string, string>;
}

/**
 * Match a path pattern against an actual path.
 * For now, only supports static path matching (no dynamic params).
 *
 * @param pattern - The route pattern (e.g., '/users')
 * @param path - The actual path to match (e.g., '/users')
 * @returns MatchResult indicating if matched and extracted params
 */
export function matchPath(pattern: string, path: string): MatchResult {
	// Normalize paths by removing trailing slashes (except root)
	const normalizedPattern = pattern === "/" ? "/" : pattern.replace(/\/$/, "");
	const normalizedPath = path === "/" ? "/" : path.replace(/\/$/, "");

	if (normalizedPattern === normalizedPath) {
		return { matched: true, params: {} };
	}

	return { matched: false, params: {} };
}
