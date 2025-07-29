import { describe, it, expect } from "vitest";
import {
  findNodeByPath,
  findParentByPath,
  applyUpdate,
  applyUpdates,
} from "../update-utils";
import type { UINode, UIElementNode, UIUpdatePayload } from "../tree";
import {
  createElementNode,
  createFragment,
  createMountPoint,
  isElementNode,
  isTextNode,
  isMountPointNode,
  getMountPointComponentKey,
} from "../tree";

describe("update-utils", () => {
  describe("findNodeByPath", () => {
    it("should find root node with empty path", () => {
      const root = createElementNode("div");
      const result = findNodeByPath(root, []);
      expect(result).toBe(root);
    });

    it("should find nested text node by path", () => {
      const textNode = "Hello";
      const childDiv = createElementNode("span", {}, [textNode]);
      const root = createElementNode("div", {}, [childDiv]);

      const result = findNodeByPath(root, [0, 0]);
      expect(result).toBe(textNode);
      expect(isTextNode(result!)).toBe(true);
    });

    it("should find nested element node by path", () => {
      const childDiv = createElementNode("span", {}, ["Hello"]);
      const root = createElementNode("div", {}, [childDiv]);

      const result = findNodeByPath(root, [0]);
      expect(result).toBe(childDiv);
      expect(isElementNode(result!)).toBe(true);
    });

    it("should return null for invalid path", () => {
      const root = createElementNode("div");
      const result = findNodeByPath(root, [0]);
      expect(result).toBeNull();
    });

    it("should return null when trying to traverse into text node", () => {
      const root = createElementNode("div", {}, ["Hello"]);
      const result = findNodeByPath(root, [0, 0]);
      expect(result).toBeNull();
    });

    it("should find mount point node by path", () => {
      const mountPoint = createMountPoint("counter", { count: 5 });
      const root = createElementNode("div", {}, [mountPoint]);

      const result = findNodeByPath(root, [0]);
      expect(result).toBe(mountPoint);
      expect(isMountPointNode(result!)).toBe(true);
    });

    it("should return null when trying to traverse into mount point node", () => {
      const mountPoint = createMountPoint("counter", { count: 5 });
      const root = createElementNode("div", {}, [mountPoint]);
      const result = findNodeByPath(root, [0, 0]);
      expect(result).toBeNull();
    });
  });

  describe("findParentByPath", () => {
    it("should return null for root path", () => {
      const root = createElementNode("div");
      const result = findParentByPath(root, []);
      expect(result).toBeNull();
    });

    it("should find parent and index", () => {
      const textNode = "Hello";
      const root = createElementNode("div", {}, [textNode]);

      const result = findParentByPath(root, [0]);
      expect(result?.parent).toBe(root);
      expect(result?.index).toBe(0);
    });

    it("should work with fragment nodes", () => {
      const fragment = createFragment(["Hello", "World"]);
      const root = createElementNode("div", {}, [fragment]);

      const result = findParentByPath(root, [0]);
      expect(result?.parent).toBe(root);
      expect(result?.index).toBe(0);
    });

    it("should work with mount point nodes", () => {
      const mountPoint = createMountPoint("counter", { count: 5 });
      const root = createElementNode("div", {}, [mountPoint]);

      const result = findParentByPath(root, [0]);
      expect(result?.parent).toBe(root);
      expect(result?.index).toBe(0);
    });
  });

  describe("applyUpdate", () => {
    it("should insert text node at specified index", () => {
      const existingChild = "Existing";
      const root = createElementNode("div", {}, [existingChild]);
      const newChild = "New";

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "insert",
        path: [],
        data: { node: newChild, index: 0 },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children).toHaveLength(2);
      expect((result as UIElementNode).children[0]).toBe("New");
      expect((result as UIElementNode).children[1]).toBe("Existing");
    });

    it("should insert element node at specified index", () => {
      const existingChild = "Existing";
      const root = createElementNode("div", {}, [existingChild]);
      const newChild = createElementNode("span", {}, ["New"]);

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "insert",
        path: [],
        data: { node: newChild, index: 0 },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children).toHaveLength(2);
      expect((result as UIElementNode).children[0]).toEqual(newChild);
      expect((result as UIElementNode).children[1]).toBe("Existing");
    });

    it("should remove node at specified index", () => {
      const child1 = "Child 1";
      const child2 = "Child 2";
      const root = createElementNode("div", {}, [child1, child2]);

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "remove",
        path: [],
        data: { index: 0 },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children).toHaveLength(1);
      expect((result as UIElementNode).children[0]).toBe("Child 2");
    });

    it("should replace text node with another text node", () => {
      const oldChild = "Old";
      const root = createElementNode("div", {}, [oldChild]);
      const newChild = "New";

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "replace",
        path: [0],
        data: { node: newChild },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children[0]).toBe("New");
    });

    it("should replace text node with element node", () => {
      const oldChild = "Old";
      const root = createElementNode("div", {}, [oldChild]);
      const newChild = createElementNode("span", {}, ["New"]);

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "replace",
        path: [0],
        data: { node: newChild },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children[0]).toEqual(newChild);
    });

    it("should update props", () => {
      const root = createElementNode("div", { className: "old" });

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "update_props",
        path: [],
        data: { props: { className: "new", id: "test" } },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).props).toEqual({
        className: "new",
        id: "test",
      });
    });

    it("should insert mount point node at specified index", () => {
      const existingChild = "Existing";
      const root = createElementNode("div", {}, [existingChild]);
      const mountPoint = createMountPoint("counter", { count: 5 });

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "insert",
        path: [],
        data: { node: mountPoint, index: 0 },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children).toHaveLength(2);
      expect((result as UIElementNode).children[0]).toEqual(mountPoint);
      expect((result as UIElementNode).children[1]).toBe("Existing");
    });

    it("should replace text node with mount point node", () => {
      const oldChild = "Old";
      const root = createElementNode("div", {}, [oldChild]);
      const mountPoint = createMountPoint("counter", { count: 5 });

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "replace",
        path: [0],
        data: { node: mountPoint },
      };

      const result = applyUpdate(root, update);
      expect((result as UIElementNode).children[0]).toEqual(mountPoint);
    });

    it("should update mount point props", () => {
      const mountPoint = createMountPoint("counter", {
        count: 5,
        color: "blue",
      });
      const root = createElementNode("div", {}, [mountPoint]);

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "update_props",
        path: [0],
        data: { props: { count: 10, color: "red", size: "large" } },
      };

      const result = applyUpdate(root, update);
      const updatedMountPoint = (result as UIElementNode)
        .children[0] as UIElementNode;
      expect(updatedMountPoint.props).toEqual({
        count: 10,
        color: "red",
        size: "large",
      });
      expect(getMountPointComponentKey(updatedMountPoint)).toBe("counter");
      expect(isMountPointNode(updatedMountPoint)).toBe(true);
    });

    it("should work with fragments", () => {
      const fragment = createFragment(["Hello"]);
      const root = createElementNode("div", {}, [fragment]);

      const update: UIUpdatePayload = {
        id: "test-update",
        type: "insert",
        path: [0],
        data: { node: "World", index: 1 },
      };

      const result = applyUpdate(root, update);
      const updatedFragment = (result as UIElementNode)
        .children[0] as UIElementNode;
      expect(updatedFragment.children).toHaveLength(2);
      expect(updatedFragment.children[0]).toBe("Hello");
      expect(updatedFragment.children[1]).toBe("World");
    });
  });

  describe("applyUpdates", () => {
    it("should apply multiple updates in sequence", () => {
      const root = createElementNode("div", { className: "old" }, []);

      const updates: UIUpdatePayload[] = [
        {
          id: "update-1",
          type: "update_props",
          path: [],
          data: { props: { className: "new" } },
        },
        {
          id: "update-2",
          type: "insert",
          path: [],
          data: { node: "Hello", index: 0 },
        },
      ];

      const result = applyUpdates(root, updates);
      expect((result as UIElementNode).props.className).toBe("new");
      expect((result as UIElementNode).children).toHaveLength(1);
      expect((result as UIElementNode).children[0]).toBe("Hello");
    });
  });
});
