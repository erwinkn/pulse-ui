import React from "react";
import { describe, it, expect, vi } from "vitest";
import { VDOMRenderer, applyUpdates } from "./renderer";

import type { VDOMNode, VDOMUpdate } from "./vdom";

function childrenArray(el: React.ReactElement): React.ReactNode[] {
  return React.Children.toArray((el.props as any)?.children);
}

describe("applyReactTreeUpdates", () => {
  function makeRenderer(
    initialCallbacks: string[] = [],
    cssModules: Record<string, Record<string, string>> = {},
    initialCssRefs: string[] = []
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
      initialCssRefs
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

    tree = applyUpdates(tree, ops, renderer);
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
    tree = applyUpdates(tree, ops, renderer);
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

    tree = applyUpdates(
      tree,
      [
        {
          type: "update_css_refs",
          path: "",
          data: { set: ["className"] },
        },
        {
          type: "update_props",
          path: "",
          data: {
            set: { className: "moduleA:button" },
          },
        },
      ],
      renderer
    );
    const button = tree as React.ReactElement;
    expect((button.props as any).className).toBe("button_hash");

    tree = applyUpdates(
      tree,
      [
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
      ],
      renderer
    );
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
    tree = applyUpdates(tree, ops, renderer);
    const root = tree as React.ReactElement;
    const rootChildren = childrenArray(root);
    const child0 = rootChildren[0] as React.ReactElement;
    const innerChildren = childrenArray(child0);
    const replaced = innerChildren[0] as React.ReactElement;
    const leafChildren = childrenArray(replaced);
    expect(replaced.type).toBe("span");
    expect(leafChildren[0]).toBe("B");
  });

  it("inserts and removes children at nested parent path", () => {
    const { renderer } = makeRenderer();
    const initialVDOM: VDOMNode = {
      tag: "div",
      children: [{ tag: "div", children: [{ tag: "span", children: ["A"] }] }],
    };
    let tree = renderer.renderNode(initialVDOM);

    // Insert at index 1 under parent path 0
    tree = applyUpdates(
      tree,
      [
        {
          type: "insert",
          path: "0",
          idx: 1,
          data: { tag: "span", children: ["B"] },
        },
      ],
      renderer
    );
    let root = tree as React.ReactElement;
    let p0 = childrenArray(root)[0] as React.ReactElement;
    let kids = childrenArray(p0);
    expect(kids).toHaveLength(2);
    expect((kids[0] as React.ReactElement).type).toBe("span");
    expect((kids[1] as React.ReactElement).type).toBe("span");

    // Remove the first child under parent path 0 (index 0)
    tree = applyUpdates(
      tree,
      [
        {
          type: "remove",
          path: "0",
          idx: 0,
        },
      ],
      renderer
    );
    root = tree as React.ReactElement;
    p0 = childrenArray(root)[0] as React.ReactElement;
    kids = childrenArray(p0);
    expect(kids).toHaveLength(1);
    const only = kids[0] as React.ReactElement;
    const onlyText = childrenArray(only)[0];
    expect(onlyText).toBe("B");
  });

  it("moves children within a nested parent (path points to parent)", () => {
    const { renderer } = makeRenderer();
    const initialVDOM: VDOMNode = {
      tag: "div",
      children: [
        {
          tag: "div",
          children: [
            { tag: "span", children: ["A"] },
            { tag: "span", children: ["B"] },
            { tag: "span", children: ["C"] },
          ],
        },
      ],
    };
    let tree = renderer.renderNode(initialVDOM);
    const ops: VDOMUpdate[] = [
      {
        type: "move",
        path: "0", // parent path
        data: { from_index: 0, to_index: 1 },
      },
    ];
    tree = applyUpdates(tree, ops, renderer);
    const root = tree as React.ReactElement;
    const p0 = childrenArray(root)[0] as React.ReactElement;
    const kids = childrenArray(p0) as React.ReactElement[];
    const texts = kids.map((k) => childrenArray(k)[0]);
    expect(texts).toEqual(["B", "A", "C"]);
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
    tree = applyUpdates(tree, ops, renderer);
    const root = tree as React.ReactElement;
    const innerDiv = childrenArray(root)[0] as React.ReactElement;
    const button = childrenArray(innerDiv)[0] as React.ReactElement;
    expect(typeof (button.props as any).onClick).toBe("function");
    (button.props as any).onClick();
    expect(invokeCallback).toHaveBeenCalledWith("/test", "0.0.onClick", []);
  });

  it("rebinds callbacks when moving siblings at root and updates keys", () => {
    const { renderer, invokeCallback } = makeRenderer([
      "0.onClick",
      "1.onClick",
    ]);
    const initialVDOM: VDOMNode = {
      tag: "div",
      children: [
        { tag: "button", props: { onClick: "$cb", id: "A" }, children: ["A"] },
        { tag: "button", props: { onClick: "$cb", id: "B" }, children: ["B"] },
      ],
    };
    let tree = renderer.renderNode(initialVDOM);
    let root = tree as React.ReactElement;
    let kids = childrenArray(root) as React.ReactElement[];
    const beforeA = (kids[0].props as any).onClick;
    const beforeB = (kids[1].props as any).onClick;

    tree = applyUpdates(
      tree,
      [{ type: "move", path: "", data: { from_index: 0, to_index: 1 } }],
      renderer
    );

    root = tree as React.ReactElement;
    kids = childrenArray(root) as React.ReactElement[];

    const afterB = (kids[0].props as any).onClick; // B moved to index 0
    const afterA = (kids[1].props as any).onClick; // A moved to index 1

    expect(afterB).not.toBe(beforeB);
    expect(afterA).not.toBe(beforeA);

    (invokeCallback as any).mockClear?.();
    afterB("x");
    afterA("y");
    expect(invokeCallback).toHaveBeenCalledWith("/test", "0.onClick", ["x"]);
    expect(invokeCallback).toHaveBeenCalledWith("/test", "1.onClick", ["y"]);
  });

  it("rebinds callbacks for nested move; unaffected siblings keep identity", () => {
    const { renderer, invokeCallback } = makeRenderer([
      "0.0.onClick",
      "0.1.onClick",
      "0.2.onClick",
    ]);
    const initialVDOM: VDOMNode = {
      tag: "div",
      children: [
        {
          tag: "div",
          children: [
            {
              tag: "button",
              props: { onClick: "$cb", id: "A" },
              children: ["A"],
            },
            {
              tag: "button",
              props: { onClick: "$cb", id: "B" },
              children: ["B"],
            },
            {
              tag: "button",
              props: { onClick: "$cb", id: "C" },
              children: ["C"],
            },
          ],
        },
      ],
    };
    let tree = renderer.renderNode(initialVDOM);
    let root = tree as React.ReactElement;
    let p0 = childrenArray(root)[0] as React.ReactElement;
    let kids = childrenArray(p0) as React.ReactElement[];

    const beforeA = (kids[0].props as any).onClick;
    const beforeB = (kids[1].props as any).onClick;
    const beforeC = (kids[2].props as any).onClick;

    tree = applyUpdates(
      tree,
      [{ type: "move", path: "0", data: { from_index: 0, to_index: 1 } }],
      renderer
    );

    root = tree as React.ReactElement;
    p0 = childrenArray(root)[0] as React.ReactElement;
    kids = childrenArray(p0) as React.ReactElement[];

    const afterB = (kids[0].props as any).onClick; // B at index 0
    const afterA = (kids[1].props as any).onClick; // A at index 1
    const afterC = (kids[2].props as any).onClick; // C unaffected at index 2

    // moved items rebind
    expect(afterB).not.toBe(beforeB);
    expect(afterA).not.toBe(beforeA);
    // unaffected item keeps identity
    expect(afterC).toBe(beforeC);

    (invokeCallback as any).mockClear?.();
    afterB();
    afterA();
    afterC();
    expect(invokeCallback).toHaveBeenCalledWith("/test", "0.0.onClick", []);
    expect(invokeCallback).toHaveBeenCalledWith("/test", "0.1.onClick", []);
    expect(invokeCallback).toHaveBeenCalledWith("/test", "0.2.onClick", []);
  });
});
