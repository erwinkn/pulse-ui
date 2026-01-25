import { describe, expect, it, vi } from "bun:test";
import React from "react";
import { VDOMRenderer } from "./renderer";

import type { VDOMNode, VDOMUpdate } from "./vdom";

function childrenArray(el: React.ReactElement): React.ReactNode[] {
	return React.Children.toArray((el.props as any)?.children);
}

describe("VDOMRenderer", () => {
	function makeRenderer(registry: Record<string, unknown> = {}) {
		const invokeCallback = vi.fn();
		const client: any = { invokeCallback };
		const renderer = new VDOMRenderer(client, "/test", registry);
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

	it("does not hydrate callbacks unless the prop is listed in eval", () => {
		const { renderer } = makeRenderer();
		const tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb" },
			// eval missing => props are treated as plain JSON
		});
		const button = tree as React.ReactElement;
		expect((button.props as any).onClick).toBe("$cb");
	});

	it("hydrates callbacks when prop is listed in eval", () => {
		const { renderer, invokeCallback } = makeRenderer();
		const tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb" },
			eval: ["onClick"],
		});
		const button = tree as React.ReactElement;
		expect(typeof (button.props as any).onClick).toBe("function");
		(button.props as any).onClick("value");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["value"]);
	});

	it("debounces callbacks when placeholder includes delay", async () => {
		const { renderer, invokeCallback } = makeRenderer();

		const tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb:30" },
			eval: ["onClick"],
		});
		const button = tree as React.ReactElement;
		(button.props as any).onClick("a");
		(button.props as any).onClick("b");

		expect(invokeCallback).not.toHaveBeenCalled();
		await new Promise((resolve) => setTimeout(resolve, 20));
		expect(invokeCallback).not.toHaveBeenCalled();
		await new Promise((resolve) => setTimeout(resolve, 40));
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["b"]);
	});

	it("keeps a pending debounced call when the delay changes", async () => {
		const { renderer, invokeCallback } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb:40" },
			eval: ["onClick"],
		});

		const button = tree as React.ReactElement;
		(button.props as any).onClick("a");

		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: { eval: ["onClick"], set: { onClick: "$cb:5" } },
			},
		]);

		expect(invokeCallback).not.toHaveBeenCalled();
		await new Promise((resolve) => setTimeout(resolve, 25));
		expect(invokeCallback).not.toHaveBeenCalled();
		await new Promise((resolve) => setTimeout(resolve, 40));
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["a"]);
	});

	it("keeps a pending debounced call when a node moves", async () => {
		const { renderer, invokeCallback } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "div",
			children: [
				{
					tag: "button",
					props: { onClick: "$cb:40" },
					eval: ["onClick"],
					children: ["A"],
				},
				{
					tag: "button",
					props: { onClick: "$cb:40" },
					eval: ["onClick"],
					children: ["B"],
				},
			],
		});
		const root = tree as React.ReactElement;
		const kids = childrenArray(root) as React.ReactElement[];
		(kids[0].props as any).onClick("value");

		expect(invokeCallback).not.toHaveBeenCalled();

		tree = renderer.applyUpdates(tree, [
			{
				type: "reconciliation",
				path: "",
				N: 2,
				new: [[], []],
				reuse: [
					[0, 1],
					[1, 0],
				],
			},
		]);

		await new Promise((resolve) => setTimeout(resolve, 60));
		expect(invokeCallback).toHaveBeenCalledWith("/test", "1.onClick", ["value"]);
	});

	it("flushes debounced callbacks when a node is replaced", () => {
		const { renderer, invokeCallback } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb:50" },
			eval: ["onClick"],
		});
		const button = tree as React.ReactElement;
		(button.props as any).onClick("value");

		expect(invokeCallback).not.toHaveBeenCalled();
		tree = renderer.applyUpdates(tree, [
			{
				type: "replace",
				path: "",
				data: { tag: "div", children: ["done"] },
			},
		]);
		const root = tree as React.ReactElement;
		expect(root.type).toBe("div");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["value"]);
	});

	it("flushes debounced callbacks when eval is cleared", () => {
		const { renderer, invokeCallback } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb:50" },
			eval: ["onClick"],
		});
		const button = tree as React.ReactElement;
		(button.props as any).onClick("value");

		expect(invokeCallback).not.toHaveBeenCalled();
		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: { eval: [] },
			},
		]);
		const root = tree as React.ReactElement;
		expect(root.type).toBe("button");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["value"]);
	});

	it("flushes pending debounced calls after switching to immediate", () => {
		const { renderer, invokeCallback } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb:50" },
			eval: ["onClick"],
		});
		const button = tree as React.ReactElement;
		(button.props as any).onClick("value");

		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: { eval: ["onClick"], set: { onClick: "$cb" } },
			},
		]);

		expect(invokeCallback).not.toHaveBeenCalled();
		renderer.flushPendingCallbacks();
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["value"]);
	});

	it("flushes pending debounced callbacks on renderer teardown", () => {
		const { renderer, invokeCallback } = makeRenderer();
		const tree = renderer.renderNode({
			tag: "button",
			props: { onClick: "$cb:50" },
			eval: ["onClick"],
		});
		const button = tree as React.ReactElement;
		(button.props as any).onClick("value");

		expect(invokeCallback).not.toHaveBeenCalled();
		renderer.flushPendingCallbacks();
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", ["value"]);
	});

	it("keeps previous eval when update_props.eval is absent", () => {
		const { renderer } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "div",
			props: {
				id: {
					t: "binary",
					op: "+",
					left: { t: "lit", value: "a" },
					right: { t: "lit", value: "b" },
				},
			},
			eval: ["id"],
		});
		const root1 = tree as React.ReactElement;
		expect((root1.props as any).id).toBe("ab");

		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: {
					set: {
						id: {
							t: "binary",
							op: "+",
							left: { t: "lit", value: "x" },
							right: { t: "lit", value: "y" },
						},
					},
					// eval absent => keep previous eval
				},
			},
		]);
		const root2 = tree as React.ReactElement;
		expect((root2.props as any).id).toBe("xy");
	});

	it("clears eval when update_props.eval is []", () => {
		const { renderer } = makeRenderer();
		let tree = renderer.renderNode({
			tag: "div",
			props: {
				id: {
					t: "binary",
					op: "+",
					left: { t: "lit", value: "a" },
					right: { t: "lit", value: "b" },
				},
			},
			eval: ["id"],
		});

		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: {
					eval: [], // clear
					set: {
						id: {
							t: "binary",
							op: "+",
							left: { t: "lit", value: "x" },
							right: { t: "lit", value: "y" },
						},
					},
				},
			},
		]);
		const root = tree as React.ReactElement;
		// Now treated as plain JSON; the value stays as the expr object.
		expect((root.props as any).id).toEqual({
			t: "binary",
			op: "+",
			left: { t: "lit", value: "x" },
			right: { t: "lit", value: "y" },
		});
	});

	it("renders render-prop subtrees when prop is listed in eval", () => {
		const { renderer } = makeRenderer();
		const tree = renderer.renderNode({
			tag: "div",
			props: { render: { tag: "span", children: ["A"] } },
			eval: ["render"],
		});
		const root = tree as React.ReactElement;
		const renderProp = (root.props as any).render as React.ReactElement;
		expect(React.isValidElement(renderProp)).toBe(true);
		expect(renderProp.type).toBe("span");
		expect(childrenArray(renderProp)[0]).toBe("A");
	});

	it("evaluates expression props when listed in eval", () => {
		const C = (_props: { items?: unknown }) => null;
		const { renderer } = makeRenderer({
			C,
		});
		const tree = renderer.renderNode({
			tag: "$$C",
			props: {
				items: {
					t: "array",
					items: [
						{ t: "lit", value: 1 },
						{ t: "lit", value: 2 },
						{ t: "lit", value: 3 },
					],
				},
			},
			eval: ["items"],
		});
		const el = tree as React.ReactElement;
		expect(el.type).toBe(C);
		expect((el.props as any).items).toEqual([1, 2, 3]);
	});

	it("evaluates expression tags", () => {
		const Header = (_props: { children?: React.ReactNode }) => null;
		const { renderer } = makeRenderer({
			AppShell: { Header },
		});
		const tree = renderer.renderNode({
			tag: {
				t: "member",
				obj: { t: "ref", key: "AppShell" },
				prop: "Header",
			},
			children: ["A"],
		});
		const el = tree as React.ReactElement;
		expect(el.type).toBe(Header);
		const kids = childrenArray(el);
		expect(kids).toHaveLength(1);
		expect(kids[0]).toBe("A");
	});


	it("rebinds callbacks after reconciliation moves (no callback registry)", () => {
		const { renderer, invokeCallback } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [
				{ tag: "button", props: { onClick: "$cb" }, eval: ["onClick"], children: ["A"] },
				{ tag: "button", props: { onClick: "$cb" }, eval: ["onClick"], children: ["B"] },
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
				], // swap
			},
		];

		tree = renderer.applyUpdates(tree, ops);
		const root = tree as React.ReactElement;
		const kids = childrenArray(root) as React.ReactElement[];

		(kids[0].props as any).onClick("from-B");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "0.onClick", ["from-B"]);

		(kids[1].props as any).onClick("from-A");
		expect(invokeCallback).toHaveBeenCalledWith("/test", "1.onClick", ["from-A"]);
	});

	it("clears children when reconciliation N=0", () => {
		const { renderer } = makeRenderer();
		const initialVDOM: VDOMNode = {
			tag: "div",
			children: [{ tag: "span", children: ["A"] }],
		};
		let tree = renderer.renderNode(initialVDOM);

		tree = renderer.applyUpdates(tree, [
			{
				type: "reconciliation",
				path: "",
				N: 0,
				new: [[], []],
				reuse: [[], []],
			},
		]);

		const root = tree as React.ReactElement;
		expect(childrenArray(root)).toHaveLength(0);
	});

	it("update_props can switch callback binding on/off by changing eval", () => {
		const { renderer, invokeCallback } = makeRenderer();
		let tree = renderer.renderNode({ tag: "button", props: { id: "x" } });

		// Turn on callback binding
		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: { eval: ["onClick"], set: { onClick: "$cb" } },
			},
		]);
		const b1 = tree as React.ReactElement;
		expect(typeof (b1.props as any).onClick).toBe("function");
		(b1.props as any).onClick(1);
		expect(invokeCallback).toHaveBeenCalledWith("/test", "onClick", [1]);

		// Clear eval => onClick becomes plain JSON "$cb"
		tree = renderer.applyUpdates(tree, [
			{
				type: "update_props",
				path: "",
				data: { eval: [], set: { onClick: "$cb" } },
			},
		]);
		const b2 = tree as React.ReactElement;
		expect((b2.props as any).onClick).toBe("$cb");
	});
});
