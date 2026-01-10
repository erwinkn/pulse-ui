export interface RouteInfo {
	pathname: string;
	hash: string;
	query: string;
	queryParams: Record<string, string>;
	pathParams: Record<string, string | string[] | undefined>;
	catchall: string[];
}
