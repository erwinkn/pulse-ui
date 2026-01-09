import { describe, expect, it } from "bun:test";
import { defaultComponentRegistry, renderVdom, resolveComponent } from "./render";

describe("Component Registry", () => {
	describe("defaultComponentRegistry", () => {
		it("contains basic HTML elements", () => {
			expect(defaultComponentRegistry.div).toBe("div");
			expect(defaultComponentRegistry.span).toBe("span");
			expect(defaultComponentRegistry.button).toBe("button");
			expect(defaultComponentRegistry.p).toBe("p");
		});

		it("contains heading elements", () => {
			expect(defaultComponentRegistry.h1).toBe("h1");
			expect(defaultComponentRegistry.h2).toBe("h2");
			expect(defaultComponentRegistry.h3).toBe("h3");
			expect(defaultComponentRegistry.h4).toBe("h4");
			expect(defaultComponentRegistry.h5).toBe("h5");
			expect(defaultComponentRegistry.h6).toBe("h6");
		});

		it("contains form elements", () => {
			expect(defaultComponentRegistry.form).toBe("form");
			expect(defaultComponentRegistry.input).toBe("input");
			expect(defaultComponentRegistry.textarea).toBe("textarea");
			expect(defaultComponentRegistry.select).toBe("select");
			expect(defaultComponentRegistry.label).toBe("label");
		});

		it("contains list elements", () => {
			expect(defaultComponentRegistry.ul).toBe("ul");
			expect(defaultComponentRegistry.ol).toBe("ol");
			expect(defaultComponentRegistry.li).toBe("li");
		});

		it("contains table elements", () => {
			expect(defaultComponentRegistry.table).toBe("table");
			expect(defaultComponentRegistry.tr).toBe("tr");
			expect(defaultComponentRegistry.td).toBe("td");
			expect(defaultComponentRegistry.th).toBe("th");
		});
	});

	describe("resolveComponent", () => {
		it("resolves existing component from registry", () => {
			const registry = { MyComponent: "my-component" };
			expect(resolveComponent("MyComponent", registry)).toBe("my-component");
		});

		it("throws clear error for unknown component", () => {
			const registry = {};
			expect(() => resolveComponent("UnknownComponent", registry)).toThrow(
				'[Pulse SSR] Unknown component: "UnknownComponent". Register it in the component registry or use a valid HTML element name.',
			);
		});
	});
});

describe("renderVdom with registry", () => {
	it("renders basic HTML elements using default registry", () => {
		const vdom = {
			tag: "div",
			children: [{ tag: "span", children: ["Hello"] }],
		};
		const html = renderVdom(vdom);
		expect(html).toBe("<div><span>Hello</span></div>");
	});

	it("renders button element", () => {
		const vdom = {
			tag: "button",
			props: { type: "submit" },
			children: ["Click me"],
		};
		const html = renderVdom(vdom);
		expect(html).toBe('<button type="submit">Click me</button>');
	});

	it("merges custom registry with default", () => {
		const CustomButton = ({ children }: { children: React.ReactNode }) => (
			<button type="button" className="custom">
				{children}
			</button>
		);
		const vdom = {
			tag: "$$CustomButton",
			children: ["Custom"],
		};
		const html = renderVdom(vdom, { registry: { CustomButton } });
		expect(html).toBe('<button type="button" class="custom">Custom</button>');
	});

	it("custom registry components override defaults", () => {
		// Custom div that adds a class
		const customDiv = "section";
		const vdom = {
			tag: "$$div",
			children: ["Content"],
		};
		const html = renderVdom(vdom, { registry: { div: customDiv } });
		expect(html).toBe("<section>Content</section>");
	});

	it("throws for unknown mount point component", () => {
		const vdom = {
			tag: "$$UnknownComponent",
			children: [],
		};
		expect(() => renderVdom(vdom)).toThrow("Missing component for mount point");
	});
});
