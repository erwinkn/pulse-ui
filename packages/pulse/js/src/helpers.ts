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
	const queryParams = new URLSearchParams(location.search);
	return {
		pathname: location.pathname,
		hash: location.hash,
		query: location.search,
		queryParams: Object.fromEntries(queryParams.entries()),
		pathParams,
		catchall,
	};
}
