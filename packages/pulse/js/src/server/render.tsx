import { renderToString } from "react-dom/server";
import { ErrorBoundary } from "../error-boundary";
import { VDOMRenderer } from "../renderer";
import {
	type Location,
	type NavigateFn,
	type Params,
	PulseRouterProvider,
} from "../router/context";
import type { ComponentRegistry, VDOM } from "../vdom";

/**
 * Route information for SSR rendering.
 */
export interface RouteInfo {
	location: Location;
	params: Params;
}

/**
 * Configuration for renderVdom.
 */
export interface RenderConfig {
	routeInfo?: RouteInfo;
	registry?: ComponentRegistry;
}

// No-op navigate function for SSR (navigation happens on the client)
const ssrNavigate: NavigateFn = (() => {}) as NavigateFn;

/**
 * Default component registry for SSR.
 * Maps string names to React components (HTML intrinsic elements).
 * Custom components can be added via config.registry.
 */
export const defaultComponentRegistry: ComponentRegistry = {
	// Basic container elements
	div: "div",
	span: "span",
	p: "p",
	section: "section",
	article: "article",
	aside: "aside",
	header: "header",
	footer: "footer",
	main: "main",
	nav: "nav",
	// Headings
	h1: "h1",
	h2: "h2",
	h3: "h3",
	h4: "h4",
	h5: "h5",
	h6: "h6",
	// Interactive elements
	button: "button",
	a: "a",
	// Form elements
	form: "form",
	input: "input",
	textarea: "textarea",
	select: "select",
	option: "option",
	label: "label",
	fieldset: "fieldset",
	legend: "legend",
	// List elements
	ul: "ul",
	ol: "ol",
	li: "li",
	dl: "dl",
	dt: "dt",
	dd: "dd",
	// Table elements
	table: "table",
	thead: "thead",
	tbody: "tbody",
	tfoot: "tfoot",
	tr: "tr",
	th: "th",
	td: "td",
	caption: "caption",
	// Media elements
	img: "img",
	video: "video",
	audio: "audio",
	source: "source",
	picture: "picture",
	canvas: "canvas",
	svg: "svg",
	// Text formatting
	strong: "strong",
	em: "em",
	b: "b",
	i: "i",
	u: "u",
	s: "s",
	mark: "mark",
	small: "small",
	sub: "sub",
	sup: "sup",
	code: "code",
	pre: "pre",
	blockquote: "blockquote",
	q: "q",
	cite: "cite",
	abbr: "abbr",
	// Other common elements
	br: "br",
	hr: "hr",
	iframe: "iframe",
	details: "details",
	summary: "summary",
	dialog: "dialog",
	figure: "figure",
	figcaption: "figcaption",
	address: "address",
	time: "time",
	progress: "progress",
	meter: "meter",
	output: "output",
	datalist: "datalist",
	// Pulse components
	ErrorBoundary: ErrorBoundary,
};

/**
 * Resolves a component from the registry by name.
 * Throws a clear error if the component is not found.
 */
export function resolveComponent(name: string, registry: ComponentRegistry): unknown {
	const component = registry[name];
	if (component === undefined) {
		throw new Error(
			`[Pulse SSR] Unknown component: "${name}". ` +
				`Register it in the component registry or use a valid HTML element name.`,
		);
	}
	return component;
}

/**
 * Renders VDOM JSON to an HTML string for SSR.
 * Wraps with PulseRouterProvider if routeInfo is provided.
 */
export function renderVdom(vdom: VDOM, config: RenderConfig = {}): string {
	// Create a minimal mock client for SSR (callbacks are not invoked server-side)
	const mockClient = {
		invokeCallback: () => {},
	} as any;

	// Merge default registry with custom registry (custom takes precedence)
	const registry: ComponentRegistry = {
		...defaultComponentRegistry,
		...(config.registry ?? {}),
	};

	const renderer = new VDOMRenderer(mockClient, "", registry);
	const reactTree = renderer.renderNode(vdom);

	// Wrap with router provider if route info is provided
	if (config.routeInfo) {
		const wrapped = (
			<PulseRouterProvider
				location={config.routeInfo.location}
				params={config.routeInfo.params}
				navigate={ssrNavigate}
			>
				{reactTree}
			</PulseRouterProvider>
		);
		return renderToString(wrapped);
	}

	return renderToString(reactTree);
}
