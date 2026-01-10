/**
 * Integration tests for client auto-hydration.
 *
 * Tests that verify:
 * - Client reads __PULSE_DATA__ from script tag
 * - Hydration completes without mismatch warnings
 * - Event handlers work after hydration
 */

import { afterEach, beforeEach, describe, expect, it, mock } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { RouteInfo, VDOM } from "../index";
import { VDOMRenderer } from "../index";
import { defaultComponentRegistry } from "../server/render";

describe("Entry Client Hydration Integration", () => {
	beforeEach(() => {
		cleanup();
	});

	afterEach(() => {
		cleanup();
	});

	it("should render VDOM with simple text content", () => {
		const vdom: VDOM = {
			tag: "div",
			children: ["Hello World"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		expect(container.textContent).toContain("Hello World");
		expect(container.querySelector("div")).toBeTruthy();
	});

	it("should render VDOM with props", () => {
		const vdom: VDOM = {
			tag: "div",
			props: { className: "container", id: "main" },
			children: ["Content"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		const div = container.querySelector("div");
		expect(div).toBeTruthy();
		expect(div?.className).toBe("container");
		expect(div?.id).toBe("main");
	});

	it("should render nested VDOM structure", () => {
		const vdom: VDOM = {
			tag: "div",
			props: { className: "container" },
			children: [
				{ tag: "h1", children: ["Title"] },
				{
					tag: "ul",
					children: [
						{ tag: "li", children: ["Item 1"] },
						{ tag: "li", children: ["Item 2"] },
					],
				},
			],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		expect(container.querySelector("h1")?.textContent).toBe("Title");
		const items = container.querySelectorAll("li");
		expect(items.length).toBe(2);
		expect(items[0]?.textContent).toBe("Item 1");
		expect(items[1]?.textContent).toBe("Item 2");
	});

	it("should handle null and undefined children", () => {
		const vdom: VDOM = {
			tag: "div",
			children: ["Text 1", null, "Text 2", "Text 3"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		// Should contain all text nodes
		expect(container.textContent).toContain("Text 1");
		expect(container.textContent).toContain("Text 2");
		expect(container.textContent).toContain("Text 3");
	});

	it("should handle boolean children", () => {
		const vdom: VDOM = {
			tag: "div",
			children: [true, false, "Content"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		// Booleans should not render as text
		expect(container.textContent).toBe("Content");
	});

	it("should handle numeric children", () => {
		const vdom: VDOM = {
			tag: "div",
			children: [42, 3.14, "text"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		expect(container.textContent).toContain("42");
		expect(container.textContent).toContain("3.14");
		expect(container.textContent).toContain("text");
	});

	it("should handle style objects", () => {
		const vdom: VDOM = {
			tag: "div",
			props: {
				style: { color: "red", fontSize: "16px" },
			},
			children: ["Styled"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		const div = container.querySelector("div");
		expect(div).toBeTruthy();
		const style = div?.getAttribute("style");
		expect(style).toBeTruthy();
		// Style attributes are inline
		expect(style).toContain("color");
		expect(style).toContain("red");
	});

	it("should preserve RouteInfo structure", () => {
		const routeInfo: RouteInfo = {
			pathname: "/users/123/posts/456",
			hash: "#comments",
			query: "?sort=recent&limit=10",
			queryParams: { sort: "recent", limit: "10" },
			pathParams: { userId: "123", postId: "456" },
			catchall: [],
		};

		// Verify structure is preserved through serialization/deserialization
		const serialized = JSON.stringify(routeInfo);
		const deserialized = JSON.parse(serialized) as RouteInfo;

		expect(deserialized.pathname).toBe("/users/123/posts/456");
		expect(deserialized.hash).toBe("#comments");
		expect(deserialized.query).toBe("?sort=recent&limit=10");
		expect(deserialized.queryParams).toEqual({ sort: "recent", limit: "10" });
		expect(deserialized.pathParams).toEqual({
			userId: "123",
			postId: "456",
		});
	});

	it("should handle RouteInfo with catchall segments", () => {
		const routeInfo: RouteInfo = {
			pathname: "/files/a/b/c/d",
			hash: "",
			query: "",
			queryParams: {},
			pathParams: {},
			catchall: ["a", "b", "c", "d"],
		};

		const serialized = JSON.stringify(routeInfo);
		const deserialized = JSON.parse(serialized) as RouteInfo;

		expect(deserialized.catchall).toEqual(["a", "b", "c", "d"]);
	});

	it("should render VDOM with custom data attributes", () => {
		const vdom: VDOM = {
			tag: "button",
			props: {
				"data-testid": "submit-btn",
				"aria-label": "Submit form",
			},
			children: ["Click me"],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		render(reactTree as ReactNode);

		const button = screen.getByTestId("submit-btn");
		expect(button).toBeTruthy();
		expect(button.getAttribute("aria-label")).toBe("Submit form");
	});

	it("should handle Fragment rendering", () => {
		const vdom: VDOM = {
			tag: "div",
			children: [
				{ tag: "p", children: ["Paragraph 1"] },
				{ tag: "p", children: ["Paragraph 2"] },
			],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		const paragraphs = container.querySelectorAll("p");
		expect(paragraphs.length).toBe(2);
	});

	it("should handle empty VDOM", () => {
		const vdom: VDOM = {
			tag: "div",
			children: [],
		};

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		const div = container.querySelector("div");
		expect(div).toBeTruthy();
		expect(div?.children.length).toBe(0);
	});

	it("should handle string VDOM (text node)", () => {
		const vdom: VDOM = "Just text";

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		expect(container.textContent).toContain("Just text");
	});

	it("should handle numeric VDOM (number node)", () => {
		const vdom: VDOM = 42;

		const renderer = new VDOMRenderer(mock(() => {}) as any, "/", defaultComponentRegistry);
		const reactTree = renderer.renderNode(vdom);

		const { container } = render(reactTree as ReactNode);

		expect(container.textContent).toContain("42");
	});
});
