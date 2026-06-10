export interface RouteInfo {
	pathname: string;
	hash: string;
	query: string;
	queryParams: Record<string, string>;
	pathParams: Record<string, string | undefined>;
	catchall: string[];
}

export interface LocationLike {
	pathname: string;
	search: string;
	hash: string;
}

export function buildRouteInfo(
	location: LocationLike,
	pathParams: Record<string, string | undefined>,
	catchall: string[],
): RouteInfo {
	const query = location.search.startsWith("?") ? location.search.slice(1) : location.search;
	const hash = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
	return {
		pathname: location.pathname,
		hash,
		query,
		queryParams: Object.fromEntries(new URLSearchParams(location.search).entries()),
		pathParams,
		catchall,
	};
}
