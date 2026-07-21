import type { Directives } from "./client";

export type DirectivesSource = Directives | (() => Directives | undefined) | undefined;

function readDirectives(source: DirectivesSource): Directives {
	if (typeof source === "function") {
		return source() ?? {};
	}
	return source ?? {};
}

export function buildPulseRequest(
	input: string | URL,
	init: RequestInit & {
		directives?: DirectivesSource;
		jsonBody?: unknown;
	} = {},
): [URL, RequestInit] {
	const { directives: directivesSource, jsonBody, headers, body, ...rest } = init;
	const directives = readDirectives(directivesSource);
	const url = input instanceof URL ? new URL(input.toString()) : new URL(input, window.location.href);

	if (directives.query) {
		for (const [key, value] of Object.entries(directives.query)) {
			url.searchParams.set(key, value);
		}
	}

	const nextHeaders = new Headers(headers);
	if (directives.headers) {
		for (const [key, value] of Object.entries(directives.headers)) {
			nextHeaders.set(key, value);
		}
	}

	let nextBody = body;
	if (jsonBody != null) {
		nextBody = typeof jsonBody === "string" ? jsonBody : JSON.stringify(jsonBody);
		if (!nextHeaders.has("content-type")) {
			nextHeaders.set("content-type", "application/json");
		}
	}

	return [
		url,
		{
			...rest,
			headers: nextHeaders,
			body: nextBody,
		},
	];
}

export function pulseFetch(
	input: string | URL,
	init: RequestInit & {
		directives?: DirectivesSource;
		jsonBody?: unknown;
	} = {},
): Promise<Response> {
	const [url, nextInit] = buildPulseRequest(input, init);
	return fetch(url, nextInit);
}
