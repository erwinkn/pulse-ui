import type { VDOM } from "../vdom";
import { type RenderConfig, renderVdom } from "./render";

const PORT = Number(process.env.PORT) || 3001;
const IS_DEV = process.env.NODE_ENV !== "production";

interface RenderRequestBody {
	vdom: VDOM;
	config?: RenderConfig;
}

/**
 * Creates a JSON error response.
 */
function errorResponse(message: string, status: number, stack?: string): Response {
	const body: { error: string; stack?: string } = { error: message };
	if (IS_DEV && stack) {
		body.stack = stack;
	}
	return new Response(JSON.stringify(body), {
		status,
		headers: { "Content-Type": "application/json" },
	});
}

/**
 * Custom error for invalid VDOM structure.
 */
export class InvalidVDOMError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "InvalidVDOMError";
	}
}

/**
 * Validates that the parsed body contains a VDOM-like structure.
 * Throws InvalidVDOMError if invalid.
 */
function validateVDOM(vdom: unknown): asserts vdom is VDOM {
	// null/undefined are valid VDOM (render nothing)
	if (vdom === null || vdom === undefined) {
		return;
	}
	// Strings and numbers are valid VDOM (text nodes)
	if (typeof vdom === "string" || typeof vdom === "number") {
		return;
	}
	// Booleans are valid VDOM (render nothing)
	if (typeof vdom === "boolean") {
		return;
	}
	// Arrays are valid VDOM (fragment of children)
	if (Array.isArray(vdom)) {
		for (const child of vdom) {
			validateVDOM(child);
		}
		return;
	}
	// Objects must have a 'tag' property (string)
	if (typeof vdom === "object") {
		if (!("tag" in vdom)) {
			throw new InvalidVDOMError('VDOM element must have a "tag" property');
		}
		if (typeof (vdom as { tag: unknown }).tag !== "string") {
			throw new InvalidVDOMError('"tag" must be a string');
		}
		// Validate children recursively if present
		const element = vdom as { tag: string; children?: unknown };
		if (element.children !== undefined) {
			if (!Array.isArray(element.children)) {
				throw new InvalidVDOMError('"children" must be an array');
			}
			for (const child of element.children) {
				validateVDOM(child);
			}
		}
		return;
	}
	throw new InvalidVDOMError(`Invalid VDOM type: ${typeof vdom}`);
}

const server = Bun.serve({
	port: PORT,
	async fetch(req) {
		const url = new URL(req.url);

		if (req.method === "GET" && url.pathname === "/health") {
			return new Response("OK", { status: 200 });
		}

		if (req.method === "POST" && url.pathname === "/render") {
			// Parse JSON body
			let body: RenderRequestBody;
			try {
				body = (await req.json()) as RenderRequestBody;
			} catch {
				return errorResponse("Malformed JSON in request body", 400);
			}

			// Validate VDOM structure
			try {
				validateVDOM(body.vdom);
			} catch (error) {
				if (error instanceof InvalidVDOMError) {
					return errorResponse(error.message, 500, IS_DEV ? error.stack : undefined);
				}
				throw error;
			}

			// Render VDOM to HTML
			try {
				const html = renderVdom(body.vdom, body.config ?? {});
				return new Response(html, {
					status: 200,
					headers: { "Content-Type": "text/html" },
				});
			} catch (error) {
				const message =
					error instanceof Error ? error.message : IS_DEV ? String(error) : "Internal server error";
				const stack = error instanceof Error ? error.stack : undefined;
				return errorResponse(message, 500, stack);
			}
		}

		return new Response("Not Found", { status: 404 });
	},
});

console.log(`SSR server listening on http://localhost:${server.port}`);
