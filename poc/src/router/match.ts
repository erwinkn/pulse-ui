/**
 * Simple exact-match route matching.
 * Returns the matched pattern or null if no match.
 */
export function matchRoute(pathname: string, patterns: string[]): string | null {
	return patterns.includes(pathname) ? pathname : null;
}
