import React from "react";

export type VdomNode =
	| string
	| number
	| null
	| {
			type: string;
			props: Record<string, unknown>;
			children: VdomNode[];
	  };

export type ComponentRegistry = Record<string, React.ComponentType<Record<string, unknown>>>;

export function renderVdom(node: VdomNode, registry: ComponentRegistry): React.ReactNode {
	// Return primitives as-is
	if (node === null || typeof node === "string" || typeof node === "number") {
		return node;
	}

	const { type, props, children } = node;

	// Look up component in registry, fallback to HTML element string
	const Component = registry[type] ?? type;

	// Recursively render children (VDOM lacks stable keys from server)
	const renderedChildren = children.map((child, index) => (
		// biome-ignore lint/suspicious/noArrayIndexKey: VDOM children lack stable keys from server
		<React.Fragment key={index}>{renderVdom(child, registry)}</React.Fragment>
	));

	return <Component {...props}>{renderedChildren}</Component>;
}
