import { describe, it, expect } from "vitest";
import type { UIElementNode, UIUpdatePayload } from "../tree";
import {
  createElementNode,
  createFragment,
  createMountPoint,
  getMountPointComponentKey,
} from "../tree";
import { applyUpdates } from "../update-utils";

describe("UI Tree Integration", () => {
  it("should handle a complete workflow of updates", () => {
    // Create initial tree using simplified structure
    const initialTree = createElementNode("div", { className: "container" }, [
      createElementNode("h1", {}, ["Title"]),
      createElementNode("p", {}, ["Content"]),
    ]);

    // Apply a series of updates like a real application would
    const updates: UIUpdatePayload[] = [
      // Replace the title text (since we no longer have update_text)
      {
        id: "update-1",
        type: "replace",
        path: [0, 0],
        data: { node: "Updated Title" },
      },
      // Add a new paragraph
      {
        id: "update-2",
        type: "insert",
        path: [],
        data: {
          node: createElementNode("p", { className: "new-paragraph" }, [
            "New paragraph added dynamically",
          ]),
          index: 2,
        },
      },
      // Update container props
      {
        id: "update-3",
        type: "update_props",
        path: [],
        data: {
          props: { className: "container updated", id: "main-container" },
        },
      },
    ];

    const updatedTree = applyUpdates(initialTree, updates);

    // Verify the updates were applied correctly
    expect((updatedTree as UIElementNode).props.className).toBe(
      "container updated"
    );
    expect((updatedTree as UIElementNode).props.id).toBe("main-container");
    expect((updatedTree as UIElementNode).children).toHaveLength(3);

    // Check title was updated (text is now a string)
    const titleText = (
      (updatedTree as UIElementNode).children[0] as UIElementNode
    ).children[0];
    expect(titleText).toBe("Updated Title");

    // Check new paragraph was added
    const newParagraph = (updatedTree as UIElementNode)
      .children[2] as UIElementNode;
    expect(newParagraph.tag).toBe("p");
    expect(newParagraph.props.className).toBe("new-paragraph");

    const newParagraphText = newParagraph.children[0];
    expect(newParagraphText).toBe("New paragraph added dynamically");
  });

  it("should work with fragments", () => {
    // Test the fragment functionality
    const initialTree = createElementNode("div", {}, [
      createFragment(["Hello", " ", "World"]),
    ]);

    const updates: UIUpdatePayload[] = [
      // Insert a new text node into the fragment
      {
        id: "update-1",
        type: "insert",
        path: [0],
        data: { node: "!", index: 3 },
      },
    ];

    const updatedTree = applyUpdates(initialTree, updates);
    const fragment = (updatedTree as UIElementNode)
      .children[0] as UIElementNode;

    expect(fragment.children).toHaveLength(4);
    expect(fragment.children[0]).toBe("Hello");
    expect(fragment.children[1]).toBe(" ");
    expect(fragment.children[2]).toBe("World");
    expect(fragment.children[3]).toBe("!");
  });

  it("should work with mount points", () => {
    // Test mount point functionality with updates
    const initialTree = createElementNode("div", { className: "app" }, [
      createElementNode("h1", {}, ["Dashboard"]),
      createMountPoint("counter", { count: 0, color: "blue" }),
      createMountPoint("user-card", { name: "John Doe", status: "offline" }),
    ]);

    const updates: UIUpdatePayload[] = [
      // Update counter props
      {
        id: "update-1",
        type: "update_props",
        path: [1],
        data: {
          props: {
            count: 5,
            color: "green",
            size: "large",
          },
        },
      },
      // Replace user card with a different mount point
      {
        id: "update-2",
        type: "replace",
        path: [2],
        data: {
          node: createMountPoint("status-badge", {
            status: "success",
            text: "Online",
          }),
        },
      },
      // Insert a new mount point
      {
        id: "update-3",
        type: "insert",
        path: [],
        data: {
          node: createMountPoint("progress-bar", {
            value: 75,
            max: 100,
            label: "Loading",
          }),
          index: 3,
        },
      },
    ];

    const updatedTree = applyUpdates(initialTree, updates);

    // Verify the updates were applied correctly
    expect((updatedTree as UIElementNode).children).toHaveLength(4);

    // Check counter props were updated
    const counter = (updatedTree as UIElementNode).children[1] as UIElementNode;
    expect(getMountPointComponentKey(counter)).toBe("counter");
    expect(counter.props).toEqual({
      count: 5,
      color: "green",
      size: "large",
    });

    // Check user card was replaced with status badge
    const statusBadge = (updatedTree as UIElementNode)
      .children[2] as UIElementNode;
    expect(getMountPointComponentKey(statusBadge)).toBe("status-badge");
    expect(statusBadge.props).toEqual({
      status: "success",
      text: "Online",
    });

    // Check progress bar was inserted
    const progressBar = (updatedTree as UIElementNode)
      .children[3] as UIElementNode;
    expect(getMountPointComponentKey(progressBar)).toBe("progress-bar");
    expect(progressBar.props).toEqual({
      value: 75,
      max: 100,
      label: "Loading",
    });
  });

  it("should handle mixed content with mount points and traditional elements", () => {
    // Test complex scenario with all node types
    const initialTree = createElementNode("div", {}, [
      "Welcome",
      createElementNode("h2", {}, ["Statistics"]),
      createFragment([
        createMountPoint("metric-card", { title: "Users", value: 100 }),
        createMountPoint("metric-card", { title: "Sales", value: 2500 }),
      ]),
    ]);

    const updates: UIUpdatePayload[] = [
      // Update first metric in fragment
      {
        id: "update-1",
        type: "update_props",
        path: [2, 0],
        data: {
          props: {
            title: "Users",
            value: 150,
            trend: "up",
            change: 50,
          },
        },
      },
      // Replace fragment with individual mount points
      {
        id: "update-2",
        type: "replace",
        path: [2],
        data: {
          node: createElementNode("div", { className: "metrics-grid" }, [
            createMountPoint("metric-card", { title: "Users", value: 150 }),
            createMountPoint("metric-card", { title: "Sales", value: 2500 }),
            createMountPoint("metric-card", {
              title: "Revenue",
              value: "$50k",
            }),
          ]),
        },
      },
    ];

    const updatedTree = applyUpdates(initialTree, updates);

    // Verify structure
    expect((updatedTree as UIElementNode).children).toHaveLength(3);
    expect((updatedTree as UIElementNode).children[0]).toBe("Welcome");

    const metricsContainer = (updatedTree as UIElementNode)
      .children[2] as UIElementNode;
    expect(metricsContainer.tag).toBe("div");
    expect(metricsContainer.props.className).toBe("metrics-grid");
    expect(metricsContainer.children).toHaveLength(3);

    // Check all metrics are mount points
    const metrics = metricsContainer.children as UIElementNode[];
    expect(getMountPointComponentKey(metrics[0])).toBe("metric-card");
    expect(getMountPointComponentKey(metrics[1])).toBe("metric-card");
    expect(getMountPointComponentKey(metrics[2])).toBe("metric-card");

    expect(metrics[0].props.title).toBe("Users");
    expect(metrics[1].props.title).toBe("Sales");
    expect(metrics[2].props.title).toBe("Revenue");
  });
});
