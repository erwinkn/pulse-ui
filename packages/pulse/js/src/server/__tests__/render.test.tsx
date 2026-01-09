import { describe, expect, it } from "bun:test";
import type { VDOM } from "../../vdom";
import { renderVdom } from "../render";

describe("SSR renderVdom", () => {
	describe("simple VDOM", () => {
		it("renders div with text child", () => {
			const vdom = { tag: "div", props: {}, children: ["Hello"] };
			const html = renderVdom(vdom);
			expect(html).toBe("<div>Hello</div>");
		});

		it("renders empty div", () => {
			const vdom = { tag: "div" };
			const html = renderVdom(vdom);
			expect(html).toBe("<div></div>");
		});

		it("renders text-only content", () => {
			const vdom = "Just text";
			const html = renderVdom(vdom);
			expect(html).toBe("Just text");
		});

		it("renders number content", () => {
			const vdom = { tag: "span", children: [42] };
			const html = renderVdom(vdom);
			expect(html).toBe("<span>42</span>");
		});
	});

	describe("nested VDOM", () => {
		it("renders single level nesting", () => {
			const vdom = {
				tag: "div",
				children: [{ tag: "span", children: ["Nested"] }],
			};
			const html = renderVdom(vdom);
			expect(html).toBe("<div><span>Nested</span></div>");
		});

		it("renders multiple levels of nesting", () => {
			const vdom = {
				tag: "div",
				children: [
					{
						tag: "section",
						children: [
							{
								tag: "article",
								children: [{ tag: "p", children: ["Deep"] }],
							},
						],
					},
				],
			};
			const html = renderVdom(vdom);
			expect(html).toBe("<div><section><article><p>Deep</p></article></section></div>");
		});

		it("renders multiple siblings", () => {
			const vdom = {
				tag: "ul",
				children: [
					{ tag: "li", children: ["First"] },
					{ tag: "li", children: ["Second"] },
					{ tag: "li", children: ["Third"] },
				],
			};
			const html = renderVdom(vdom);
			expect(html).toBe("<ul><li>First</li><li>Second</li><li>Third</li></ul>");
		});

		it("renders mixed text and element children", () => {
			const vdom = {
				tag: "p",
				children: ["Hello ", { tag: "strong", children: ["world"] }, "!"],
			};
			const html = renderVdom(vdom);
			expect(html).toBe("<p>Hello <strong>world</strong>!</p>");
		});
	});

	describe("props application", () => {
		it("applies className prop", () => {
			const vdom = {
				tag: "div",
				props: { className: "container" },
				children: ["Content"],
			};
			const html = renderVdom(vdom);
			expect(html).toBe('<div class="container">Content</div>');
		});

		it("applies id prop", () => {
			const vdom = {
				tag: "div",
				props: { id: "main" },
				children: ["Content"],
			};
			const html = renderVdom(vdom);
			expect(html).toBe('<div id="main">Content</div>');
		});

		it("applies multiple props", () => {
			const vdom = {
				tag: "div",
				props: { id: "wrapper", className: "box primary" },
				children: ["Content"],
			};
			const html = renderVdom(vdom);
			// React may order attributes differently, check both are present
			expect(html).toContain('id="wrapper"');
			expect(html).toContain('class="box primary"');
			expect(html).toContain(">Content</div>");
		});

		it("applies data attributes", () => {
			const vdom = {
				tag: "div",
				props: { "data-testid": "my-element", "data-value": "123" },
				children: [],
			};
			const html = renderVdom(vdom);
			expect(html).toContain('data-testid="my-element"');
			expect(html).toContain('data-value="123"');
		});

		it("applies boolean attributes", () => {
			const vdom = {
				tag: "input",
				props: { type: "checkbox", disabled: true, checked: true },
			};
			const html = renderVdom(vdom);
			expect(html).toContain('type="checkbox"');
			expect(html).toContain("disabled");
			expect(html).toContain("checked");
		});

		it("applies style as object", () => {
			const vdom = {
				tag: "div",
				props: { style: { color: "red", fontSize: "16px" } },
				children: ["Styled"],
			};
			const html = renderVdom(vdom);
			expect(html).toContain("color:red");
			expect(html).toContain("font-size:16px");
		});

		it("applies href and target to anchor", () => {
			const vdom = {
				tag: "a",
				props: { href: "https://example.com", target: "_blank" },
				children: ["Link"],
			};
			const html = renderVdom(vdom);
			expect(html).toBe('<a href="https://example.com" target="_blank">Link</a>');
		});
	});

	describe("complex structures", () => {
		it("renders a form with multiple inputs", () => {
			const vdom: VDOM = {
				tag: "form",
				props: { className: "login-form" },
				children: [
					{
						tag: "label",
						props: { htmlFor: "email" },
						children: ["Email:"],
					},
					{
						tag: "input",
						props: { type: "email", id: "email", name: "email" },
					},
					{
						tag: "button",
						props: { type: "submit" },
						children: ["Submit"],
					},
				],
			};
			const html = renderVdom(vdom);
			expect(html).toContain('class="login-form"');
			expect(html).toContain('for="email"');
			expect(html).toContain('type="email"');
			expect(html).toContain('type="submit"');
			expect(html).toContain(">Submit</button>");
		});

		it("renders a table structure", () => {
			const vdom = {
				tag: "table",
				children: [
					{
						tag: "thead",
						children: [
							{
								tag: "tr",
								children: [
									{ tag: "th", children: ["Name"] },
									{ tag: "th", children: ["Age"] },
								],
							},
						],
					},
					{
						tag: "tbody",
						children: [
							{
								tag: "tr",
								children: [
									{ tag: "td", children: ["Alice"] },
									{ tag: "td", children: ["30"] },
								],
							},
						],
					},
				],
			};
			const html = renderVdom(vdom);
			expect(html).toContain("<thead>");
			expect(html).toContain("<th>Name</th>");
			expect(html).toContain("<tbody>");
			expect(html).toContain("<td>Alice</td>");
		});
	});
});
