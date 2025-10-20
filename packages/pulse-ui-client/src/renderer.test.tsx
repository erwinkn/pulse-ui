import { describe, expect, it, vi } from "bun:test";
import React from "react";
import { VDOMRenderer } from "./renderer";

import type { VDOMNode, VDOMUpdate } from "./vdom";

function childrenArray(el: React.ReactElement): React.ReactNode[] {
	return React.Children.toArray((el.props as any)?.children);
}

describe("applyReactTreeUpdates", () => {
	function makeRenderer(
		initialCallbacks: string[] = [],
		cssModules: Record<string, Record<string, string>> = {},
		initialCssRefs: string[] = [],
	) {
		const invokeCallback = vi.fn();
		const client: any = { invokeCallback };
		const renderer = new VDOMRenderer(
			client,
			"/test",
			{},
			cssModules,
			initialCallbacks,
			[],
			initialCssRefs,
		);
		return { renderer, invokeCallback };
	}

	it("replaces the root element", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [{ tag: "span", children: ["A"] }],
		};
		let tree = renderer.renderNode(initialVDOM);

		const ops: VDOMUpdate[] = [
			{
				type: "replace",
				path: "",
				data: { tag: "div", props: { id: "root" }, children: ["B"] },
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		expect(root.type).toBe("div");
		expect((root.props as any).id).toBe("root");
		const kids = childrenArray(root);
		expect(kids).toHaveLength(1);
		expect(kids[0]).toBe("B");
	});

	it("hydrates callbacks from initial map", () => {
		const { renderer, invokeCallback } = makeRenderer(["onClick"]);
		const tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb" },
		});
		const button = tree as React.ReactElement;
		expect(typeof (button.props as any).onClick).toBe("function");
		(button.props as any).onClick("value");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["value"]);
	});

	it("updates root props and maps callbacks", () => {
		const { renderer, invokeCallback } = makeRenderer();
		const initialVDOM: VDOMNode = { tag: "div", children: [] };
		let tree = renderer.renderNode(initialVDOM);
		const ops: VDOMUpdate[] = [
			{
				type: "update_props",
				path: "",
				data: { set: { id: "root" } },
			},
			{
				type: "update_callbacks",
				path: "",
				data: { add: ["onClick"] },
			},
			{
				type: "update_props",
				path: "",
				data: { set: { onClick: "$cb" } },
			},
		];
		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		expect((root.props as any).id).toBe("root");
		expect(typeof (root.props as any).onClick).toBe("function");
		(root.props as any).onClick(123);
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", [123]);
	});

	it("hydrates css refs from initial payload", () => {
		const cssModules = { moduleA: { container: "container_hash" } };
		const { renderer } = makeRenderer([], cssModules, ["className"]);
		const tree = renderer.renderNode({
			tag: "div",
			props: {
				className: "moduleA:container",
			},
		});
		const el = tree as React.ReactElement;
		expect((el.props as any).className).toBe("container_hash");
	});

	it("applies css ref deltas", () => {
		const cssModules = { moduleA: { button: "button_hash" } };
		const { renderer } = makeRenderer([], cssModules);
		const initialVDOM: VDOMNode = { tag: "button" };
		let tree = renderer.renderNode(initialVDOM);

		tree = renderer.applyUpdates(tree, [
			{
				type: "update_css_refs",
				path: "",
				data: { add: ["className"] },
			},
			{
				type: "update_props",
				path: "",
				data: {
					set: { className: "moduleA:button" },
				},
			},
		]);
		const button = tree as React.ReactElement;
		expect((button.props as any).className).toBe("button_hash");

		tree = renderer.applyUpdates(tree, [
			{
				type: "update_css_refs",
				path: "",
				data: { remove: ["className"] },
			},
			{
				type: "update_props",
				path: "",
				data: {
					set: { className: "plain" },
				},
			},
		]);
		const updatedButton = tree as React.ReactElement;
		expect((updatedButton.props as any).className).toBe("plain");
	});

	it("replaces a nested child via path", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [{ tag: "div", children: [{ tag: "span", children: ["A"] }] }],
		};
		let tree = renderer.renderNode(initialVDOM);
		const ops: VDOMUpdate[] = [
			{
				type: "replace",
				path: "0.0",
				data: { tag: "span", children: ["B"] },
			},
		];
		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const rootChildren = childrenArray(root);
		const child0 = rootChildren[0] as React.ReactElement;
		const innerChildren = childrenArray(child0);
		const replaced = innerChildren[0] as React.ReactElement;
		const leafChildren = childrenArray(replaced);
		expect(replaced.type).toBe("span");
		expect(leafChildren[0]).toBe("B");
	});

	it("applies reconciliation with new items", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{ tag: "span", children: ["A"] },
				{ tag: "span", children: ["B"] },
			],
		};
		let tree = renderer.renderNode(initialVDOM);

		const ops: VDOMUpdate[] = [
			{
				type: "reconciliation",
				path: "",
				N: 3,
				new: [[2], [{ tag: "span", children: ["C"] }]],
				reuse: [
					[0, 1],
					[0, 1],
				],
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const kids = childrenArray(root) as React.ReactElement[];
		expect(kids).toHaveLength(3);
		expect(childrenArray(kids[0])[0]).toBe("A");
		expect(childrenArray(kids[1])[0]).toBe("B");
		expect(childrenArray(kids[2])[0]).toBe("C");
	});

	it("applies reconciliation with moves", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{ tag: "span", children: ["A"] },
				{ tag: "span", children: ["B"] },
				{ tag: "span", children: ["C"] },
			],
		};
		let tree = renderer.renderNode(initialVDOM);

		const ops: VDOMUpdate[] = [
			{
				type: "reconciliation",
				path: "",
				N: 3,
				new: [[], []],
				reuse: [
					[0, 2],
					[2, 0],
				], // Move A to index 2, C to index 0
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const kids = childrenArray(root) as React.ReactElement[];
		expect(kids).toHaveLength(3);
		expect(childrenArray(kids[0])[0]).toBe("C");
		expect(childrenArray(kids[1])[0]).toBe("B");
		expect(childrenArray(kids[2])[0]).toBe("A");
	});

	it("applies reconciliation with mixed new items and moves", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{ tag: "span", children: ["A"] },
				{ tag: "span", children: ["B"] },
				{ tag: "span", children: ["C"] },
			],
		};
		let tree = renderer.renderNode(initialVDOM);

		const ops: VDOMUpdate[] = [
			{
				type: "reconciliation",
				path: "",
				N: 4,
				new: [
					[1, 3],
					[
						{ tag: "span", children: ["D"] },
						{ tag: "span", children: ["E"] },
					],
				],
				reuse: [
					[0, 2],
					[0, 2],
				], // Keep A at 0, C at 2
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const kids = childrenArray(root) as React.ReactElement[];
		expect(kids).toHaveLength(4);
		expect(childrenArray(kids[0])[0]).toBe("A");
		expect(childrenArray(kids[1])[0]).toBe("D");
		expect(childrenArray(kids[2])[0]).toBe("C");
		expect(childrenArray(kids[3])[0]).toBe("E");
	});

	it("applies reconciliation with callback rebinding", () => {
		const { renderer, invokeCallback } = makeRenderer(["0.onClick", "1.onClick"]);
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{ tag: "button", props: { onClick: "$cb" }, children: ["A"] },
				{ tag: "button", props: { onClick: "$cb" }, children: ["B"] },
			],
		};
		let tree = renderer.renderNode(initialVDOM);

		const ops: VDOMUpdate[] = [
			{
				type: "reconciliation",
				path: "",
				N: 2,
				new: [[], []],
				reuse: [
					[0, 1],
					[1, 0],
				], // Swap positions
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const kids = childrenArray(root) as React.ReactElement[];

		// Test that callbacks are properly rebound
		(kids[0].props as any).onClick("from-B");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "0.onClick", ["from-B"]);

		(kids[1].props as any).onClick("from-A");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "1.onClick", ["from-A"]);
	});

	it("applies reconciliation with nested path", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{
					tag: "div",
					children: [
						{ tag: "span", children: ["A"] },
						{ tag: "span", children: ["B"] },
					],
				},
			],
		};
		let tree = renderer.renderNode(initialVDOM);

		const ops: VDOMUpdate[] = [
			{
				type: "reconciliation",
				path: "0",
				N: 3,
				new: [[2], [{ tag: "span", children: ["C"] }]],
				reuse: [
					[0, 1],
					[0, 1],
				],
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const innerDiv = childrenArray(root)[0] as React.ReactElement;
		const kids = childrenArray(innerDiv) as React.ReactElement[];
		expect(kids).toHaveLength(3);
		expect(childrenArray(kids[0])[0]).toBe("A");
		expect(childrenArray(kids[1])[0]).toBe("B");
		expect(childrenArray(kids[2])[0]).toBe("C");
	});

	it("applies nested callback additions via update", () => {
		const { renderer, invokeCallback } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{
					tag: "div",
					children: [{ tag: "button", props: { id: "btn" }, children: ["X"] }],
				},
			],
		};
		let tree = renderer.renderNode(initialVDOM);
		const ops: VDOMUpdate[] = [
			{
				type: "update_callbacks",
				path: "",
				data: { add: ["0.0.onClick"] },
			},
			{
				type: "update_props",
				path: "0.0",
				data: { set: { onClick: "$cb" } },
			},
		];
		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const innerDiv = childrenArray(root)[0] as React.ReactElement;
		const button = childrenArray(innerDiv)[0] as React.ReactElement;
		expect(typeof (button.props as any).onClick).toBe("function");
		(button.props as any).onClick();
		expect(invokeCallback).toHaveBeenCalledWith("/test", "0.0.onClick", []);
	});
});
