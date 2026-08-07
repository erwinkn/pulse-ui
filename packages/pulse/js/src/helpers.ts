import type { LoaderFunctionArgs } from "react-router";

/** The URL this tab is displaying. Route-match data (pathParams/catchall)
 * is derived server-side per mount; the client only ever reports the URL. */
export interface PulseLocation {
	pathname: string;
	hash: string;
	query: string;
	queryParams: Record<string, string>;
}

export function extractServerLocation({ request }: LoaderFunctionArgs) {
	const parsedUrl = new URL(request.url);
	const query = parsedUrl.search.startsWith("?")
		? parsedUrl.search.slice(1)
		: parsedUrl.search;
	const hash = parsedUrl.hash.startsWith("#")
		? parsedUrl.hash.slice(1)
		: parsedUrl.hash;

	return {
		hash,
		pathname: parsedUrl.pathname,
		query,
		queryParams: Object.fromEntries(parsedUrl.searchParams.entries()),
	} satisfies PulseLocation;
}
