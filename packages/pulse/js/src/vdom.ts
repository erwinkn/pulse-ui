// =============================================================================
// VDOM (structural expressions + eval-keyed props)
// =============================================================================

export const FRAGMENT_TAG = "";
export const MOUNT_POINT_PREFIX = "$$";

// Unified registry: mount-point key -> React component (or any registry object).
export type ComponentRegistry = Record<string, any>;

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
	items: VDOMNode[];
}

export interface ObjectExpr {
	t: "object";
	props: Record<string, VDOMNode>;
}

export interface MemberExpr {
	t: "member";
	obj: VDOMNode;
	prop: string;
}

export interface SubscriptExpr {
	t: "sub";
	obj: VDOMNode;
	key: VDOMNode;
}

export interface CallExpr {
	t: "call";
	callee: VDOMNode;
	args: VDOMNode[];
}

export interface UnaryExpr {
	t: "unary";
	op: string;
	arg: VDOMNode;
}

export interface BinaryExpr {
	t: "binary";
	op: string;
	left: VDOMNode;
	right: VDOMNode;
}

export interface TernaryExpr {
	t: "ternary";
	cond: VDOMNode;
	then: VDOMNode;
	else_: VDOMNode;
}

export interface TemplateExpr {
	t: "template";
	parts: Array<string | VDOMNode>;
}

export interface ArrowExpr {
	t: "arrow";
	params: string[];
	body: VDOMNode;
}

export interface NewExpr {
	t: "new";
	ctor: VDOMNode;
	args: VDOMNode[];
}

// -----------------------------------------------------------------------------
// VDOM tree
// -----------------------------------------------------------------------------

export type CallbackPlaceholder = "$cb" | `$cb:${number}`;

export type RefToken = `#ref:${string},${string}`;

export type VDOMPropValue =
	| JsonValue
	| VDOMExpr
	| VDOMElement
	| CallbackPlaceholder
	| RefToken;

export interface VDOMElement {
	tag: string | VDOMExpr;
	key?: string;
	props?: Record<string, VDOMPropValue>;
	children?: VDOMNode[];
	// Prop keys that should be interpreted (expr / render-prop subtree / callback binding).
	// When absent, props are treated as plain JSON.
	eval?: string[];
}

export type VDOMNode = JsonPrimitive | VDOMElement | VDOMExpr;
export type VDOM = VDOMNode;

export function isElementNode(node: VDOMNode): node is VDOMElement {
	return typeof node === "object" && node !== null && "tag" in node;
}

export function isExprNode(node: unknown): node is VDOMExpr {
	return typeof node === "object" && node !== null && "t" in (node as any);
}

export function isMountPointNode(node: VDOMNode): node is VDOMElement {
	return (
		isElementNode(node) &&
		typeof node.tag === "string" &&
		node.tag.startsWith(MOUNT_POINT_PREFIX) &&
		node.tag !== FRAGMENT_TAG
	);
}

// -----------------------------------------------------------------------------
// Updates
// -----------------------------------------------------------------------------

export interface VDOMUpdateBase {
	type: string;
	path: string;
}

export interface ReplaceUpdate extends VDOMUpdateBase {
	type: "replace";
	data: VDOM;
}

export interface UpdatePropsUpdate extends VDOMUpdateBase {
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

export interface ReconciliationUpdate {
	type: "reconciliation";
	path: string;
	N: number;
	new: [number[], VDOM[]];
	reuse: [number[], number[]];
}

export type VDOMUpdate = ReplaceUpdate | UpdatePropsUpdate | ReconciliationUpdate;
