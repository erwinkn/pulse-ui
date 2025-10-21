import type { LoaderFunctionArgs } from "react-router";

export interface RouteInfo {
	pathname: string;
	hash: string;
	query: string;
	queryParams: Record<string, string>;
	pathParams: Record<string, string | undefined>;
	catchall: string[];
}

export function extractServerRouteInfo({ params, request }: LoaderFunctionArgs) {
	const { "*": catchall = "", ...pathParams } = params;
	const parsedUrl = new URL(request.url);

	return {
		hash: parsedUrl.hash,
		pathname: parsedUrl.pathname,
		query: parsedUrl.search,
		queryParams: Object.fromEntries(parsedUrl.searchParams.entries()),
		pathParams,
		catchall: catchall.length > 1 ? catchall.split("/") : [],
	} satisfies RouteInfo;
}
