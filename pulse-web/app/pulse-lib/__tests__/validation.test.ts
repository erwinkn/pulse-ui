import { describe, it, expect } from "vitest";
import { createElementNode, FRAGMENT_TAG, MOUNT_POINT_PREFIX } from "../tree";

describe("UI Tree Validation", () => {
  it("should throw error when user tries to use reserved fragment tag", () => {
    expect(() => {
      createElementNode(FRAGMENT_TAG, {}, ["Should not work"]);
    }).toThrow(
      `Tags starting with '${MOUNT_POINT_PREFIX}' are reserved for internal use. Please use a different tag name.`
    );
  });

  it("should throw error when user tries to use reserved mount point prefix", () => {
    expect(() => {
      createElementNode("$$custom-component", {}, ["Should not work"]);
    }).toThrow(
      `Tags starting with '${MOUNT_POINT_PREFIX}' are reserved for internal use. Please use a different tag name.`
    );
  });

  it("should allow creating elements with regular tags", () => {
    expect(() => {
      createElementNode("div", {}, ["Should work fine"]);
    }).not.toThrow();
  });

  it("should show the actual reserved prefix in error message", () => {
    try {
      createElementNode(FRAGMENT_TAG, {}, []);
    } catch (error) {
      expect((error as Error).message).toContain("$$");
    }
  });
});
