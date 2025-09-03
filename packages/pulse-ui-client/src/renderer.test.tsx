import React from "react";
import { describe, it, expect, vi } from "vitest";
import { VDOMRenderer, applyReactTreeUpdates } from "./renderer";

import type { VDOMNode, VDOMUpdate } from "./vdom";

function childrenArray(el: React.ReactElement): React.ReactNode[] {
  return React.Children.toArray((el.props as any)?.children);
}

describe("applyReactTreeUpdates", () => {
  function makeRenderer() {
    const invokeCallback = vi.fn();
    const client: any = { invokeCallback };
    const renderer = new VDOMRenderer(client, "/test", {});
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

    tree = applyReactTreeUpdates(tree, ops, renderer);
    const root = tree as React.ReactElement;
    expect(root.type).toBe("div");
    expect((root.props as any).id).toBe("root");
    const kids = childrenArray(root);
    expect(kids).toHaveLength(1);
    expect(kids[0]).toBe("B");
  });

  it("updates root props and maps callbacks", () => {
    const { renderer, invokeCallback } = makeRenderer();
    const initialVDOM: VDOMNode = { tag: "div", children: [] };
    let tree = renderer.renderNode(initialVDOM);
    const ops: VDOMUpdate[] = [
      {
        type: "update_props",
        path: "",
        data: { id: "root", onClick: "$$fn:cb" },
      },
    ];
    tree = applyReactTreeUpdates(tree, ops, renderer);
    const root = tree as React.ReactElement;
    expect((root.props as any).id).toBe("root");
    expect(typeof (root.props as any).onClick).toBe("function");
    (root.props as any).onClick(123);
    expect(invokeCallback).toHaveBeenCalledWith("/test", "cb", [123]);
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
    tree = applyReactTreeUpdates(tree, ops, renderer);
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
    tree = applyReactTreeUpdates(
      tree,
      [
        {
          type: "insert",
          path: "0.1",
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
    tree = applyReactTreeUpdates(
      tree,
      [
        {
          type: "remove",
          path: "0.0",
        } as VDOMUpdate,
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
    tree = applyReactTreeUpdates(tree, ops, renderer);
    const root = tree as React.ReactElement;
    const p0 = childrenArray(root)[0] as React.ReactElement;
    const kids = childrenArray(p0) as React.ReactElement[];
    const texts = kids.map((k) => childrenArray(k)[0]);
    expect(texts).toEqual(["B","A", "C"]);
  });
});
