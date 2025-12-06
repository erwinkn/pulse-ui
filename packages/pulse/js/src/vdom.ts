import type { ComponentType } from "react";

// Special prefixes for reserved node types
export const FRAGMENT_TAG = "$$fragment";
export const MOUNT_POINT_PREFIX = "$$";

// export type LazyComponent = () => Promise<{ default: ComponentType<any> }>;
export type RegistryEntry = ComponentType<any>;
export type ComponentRegistry = Record<string, ComponentType<any>>;

export interface VDOMElement {
	tag: string;
	props?: Record<string, any>;
	children?: VDOMNode[];
	key?: string;
	lazy?: boolean;
}

// Primitive nodes that can be rendered
export type PrimitiveNode = string | number | boolean;

// VDOMNode is either a primitive (string, number, boolean) or an element node.
// Booleans are valid children in React but do not render anything.
// Mount points are just UIElementNodes with tags starting with $$ComponentKey
export type VDOMNode = PrimitiveNode | VDOMElement;

export type VDOM = VDOMNode;

export interface VDOMUpdateBase {
	type: string;
	path: string; // Dot-separated path to the node
}

export interface ReplaceUpdate extends VDOMUpdateBase {
	type: "replace";
	data: VDOMNode; // The new node
}

export interface UpdatePropsUpdate extends VDOMUpdateBase {
	type: "update_props";
	data: {
		set?: Record<string, any>;
		remove?: string[];
	};
}

export interface ReconciliationUpdate {
	type: "reconciliation";
	path: string;
	N: number;
	new: [number[], VDOM[]];
	reuse: [number[], number[]];
}

export interface PathDelta {
	add?: string[];
	remove?: string[];
}

export interface UpdateCallbacksUpdate extends VDOMUpdateBase {
	type: "update_callbacks";
	data: PathDelta;
}

export interface UpdateRenderPropsUpdate extends VDOMUpdateBase {
	type: "update_render_props";
	data: PathDelta;
}

export interface UpdateJsExprPathsUpdate extends VDOMUpdateBase {
	type: "update_jsexpr_paths";
	data: PathDelta;
}

export type VDOMUpdate =
	| ReplaceUpdate
	| UpdatePropsUpdate
	| ReconciliationUpdate
	| UpdateCallbacksUpdate
	| UpdateRenderPropsUpdate
	| UpdateJsExprPathsUpdate;

export type UpdateType = VDOMUpdate["type"];

// Utility functions for working with the UI tree structure
export function isElementNode(node: VDOMNode): node is VDOMElement {
	// Matches all non-text nodes
	return typeof node === "object" && node !== null;
}

export function isMountPointNode(node: VDOMNode): node is VDOMElement {
	return (
		typeof node === "object" &&
		node !== null &&
		node.tag.startsWith(MOUNT_POINT_PREFIX) &&
		node.tag !== FRAGMENT_TAG
	);
}

export function isTextNode(node: VDOMNode): node is string {
	return typeof node === "string";
}

export function isFragment(node: VDOMNode): boolean {
	return typeof node === "object" && node !== null && node.tag === FRAGMENT_TAG;
}
