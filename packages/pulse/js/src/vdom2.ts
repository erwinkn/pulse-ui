// =============================================================================
// VDOM v2 (structural expressions + eval-keyed props)
// =============================================================================

export const FRAGMENT_TAG = "$$fragment";
export const MOUNT_POINT_PREFIX = "$$";

// Unified registry: mount-point key -> React component (or any registry object).
export type ComponentRegistry = Record<string, unknown>;

// -----------------------------------------------------------------------------
// JSON types
// -----------------------------------------------------------------------------

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [k: string]: JsonValue };

// -----------------------------------------------------------------------------
// Expression tree (client-evaluable)
// -----------------------------------------------------------------------------

export type VDOMExpr =
	| RegistryRefExpr
	| IdentifierExpr
	| LiteralExpr
	| UndefinedExpr
	| ArrayExpr
	| ObjectExpr
	| MemberExpr
	| SubscriptExpr
	| CallExpr
	| UnaryExpr
	| BinaryExpr
	| TernaryExpr
	| TemplateExpr
	| ArrowExpr
	| NewExpr;

export interface RegistryRefExpr {
	t: "ref";
	key: string;
}

export interface IdentifierExpr {
	t: "id";
	name: string;
}

export interface LiteralExpr {
	t: "lit";
	value: JsonPrimitive;
}

export interface UndefinedExpr {
	t: "undef";
}

export interface ArrayExpr {
	t: "array";
	items: VDOMExpr[];
}

export interface ObjectExpr {
	t: "object";
	props: Record<string, VDOMExpr>;
}

export interface MemberExpr {
	t: "member";
	obj: VDOMExpr;
	prop: string;
}

export interface SubscriptExpr {
	t: "sub";
	obj: VDOMExpr;
	key: VDOMExpr;
}

export interface CallExpr {
	t: "call";
	callee: VDOMExpr;
	args: VDOMExpr[];
}

export interface UnaryExpr {
	t: "unary";
	op: string;
	arg: VDOMExpr;
}

export interface BinaryExpr {
	t: "binary";
	op: string;
	left: VDOMExpr;
	right: VDOMExpr;
}

export interface TernaryExpr {
	t: "ternary";
	cond: VDOMExpr;
	then: VDOMExpr;
	else_: VDOMExpr;
}

export interface TemplateExpr {
	t: "template";
	parts: Array<string | VDOMExpr>;
}

export interface ArrowExpr {
	t: "arrow";
	params: string[];
	body: VDOMExpr;
}

export interface NewExpr {
	t: "new";
	ctor: VDOMExpr;
	args: VDOMExpr[];
}

// -----------------------------------------------------------------------------
// VDOM tree
// -----------------------------------------------------------------------------

export type CallbackPlaceholder = "$cb";

export type VDOMPropValue = JsonValue | VDOMExpr | VDOMElement | CallbackPlaceholder;

export interface VDOMElement {
	tag: string;
	key?: string;
	props?: Record<string, VDOMPropValue>;
	children?: VDOMNode[];
	// Prop keys that should be interpreted (expr / render-prop subtree / callback binding).
	// When absent, props are treated as plain JSON.
	eval?: string[];
}

export type VDOMNode = JsonPrimitive | VDOMElement | VDOMExpr;
export type VDOM = VDOMNode;

export function isElementNode2(node: VDOMNode): node is VDOMElement {
	return typeof node === "object" && node !== null && "tag" in node;
}

export function isExprNode2(node: unknown): node is VDOMExpr {
	return typeof node === "object" && node !== null && "t" in (node as any);
}

export function isMountPointNode2(node: VDOMNode): node is VDOMElement {
	return (
		isElementNode2(node) && node.tag.startsWith(MOUNT_POINT_PREFIX) && node.tag !== FRAGMENT_TAG
	);
}

// -----------------------------------------------------------------------------
// Updates
// -----------------------------------------------------------------------------

export interface VDOMUpdateBase {
	type: string;
	path: string;
}

export interface ReplaceUpdate2 extends VDOMUpdateBase {
	type: "replace";
	data: VDOM;
}

export interface UpdatePropsUpdate2 extends VDOMUpdateBase {
	type: "update_props";
	data: {
		set?: Record<string, VDOMPropValue>;
		remove?: string[];
		// Replace the eval list for this element.
		// - absent/undefined: keep previous
		// - []: clear
		eval?: string[];
	};
}

export interface ReconciliationUpdate2 {
	type: "reconciliation";
	path: string;
	N: number;
	new: [number[], VDOM[]];
	reuse: [number[], number[]];
}

export type VDOMUpdate2 = ReplaceUpdate2 | UpdatePropsUpdate2 | ReconciliationUpdate2;
