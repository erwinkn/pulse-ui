import { describe, expect, it } from "bun:test";
import { InvalidVDOMError } from "../server";

/**
 * Validates VDOM structure.
 * Mirrors the validateVDOM function from server.ts for testing.
 */
function validateVDOM(vdom: unknown): void {
	if (vdom === null || vdom === undefined) return;
	if (typeof vdom === "string" || typeof vdom === "number") return;
	if (typeof vdom === "boolean") return;
	if (Array.isArray(vdom)) {
		for (const child of vdom) {
			validateVDOM(child);
		}
		return;
	}
	if (typeof vdom === "object") {
		if (!("tag" in vdom)) {
			throw new InvalidVDOMError('VDOM element must have a "tag" property');
		}
		if (typeof (vdom as { tag: unknown }).tag !== "string") {
			throw new InvalidVDOMError('"tag" must be a string');
		}
		const element = vdom as { tag: string; children?: unknown };
		if (element.children !== undefined) {
			if (!Array.isArray(element.children)) {
				throw new InvalidVDOMError('"children" must be an array');
			}
			for (const child of element.children) {
				validateVDOM(child);
			}
		}
		return;
	}
	throw new InvalidVDOMError(`Invalid VDOM type: ${typeof vdom}`);
}

describe("SSR server error handling", () => {
	describe("InvalidVDOMError", () => {
		it("is an Error instance", () => {
			const error = new InvalidVDOMError("test message");
			expect(error).toBeInstanceOf(Error);
			expect(error.name).toBe("InvalidVDOMError");
			expect(error.message).toBe("test message");
		});
	});

	describe("VDOM validation", () => {
		describe("valid VDOM", () => {
			it("accepts null", () => {
				expect(() => validateVDOM(null)).not.toThrow();
			});

			it("accepts undefined", () => {
				expect(() => validateVDOM(undefined)).not.toThrow();
			});

			it("accepts string", () => {
				expect(() => validateVDOM("Hello")).not.toThrow();
			});

			it("accepts number", () => {
				expect(() => validateVDOM(42)).not.toThrow();
			});

			it("accepts boolean", () => {
				expect(() => validateVDOM(true)).not.toThrow();
				expect(() => validateVDOM(false)).not.toThrow();
			});

			it("accepts empty array", () => {
				expect(() => validateVDOM([])).not.toThrow();
			});

			it("accepts array of valid children", () => {
				expect(() =>
					validateVDOM([
						{ tag: "span", children: ["First"] },
						{ tag: "span", children: ["Second"] },
					]),
				).not.toThrow();
			});

			it("accepts object with tag property", () => {
				expect(() => validateVDOM({ tag: "div" })).not.toThrow();
			});

			it("accepts object with tag and props", () => {
				expect(() => validateVDOM({ tag: "div", props: { className: "test" } })).not.toThrow();
			});

			it("accepts object with tag and children array", () => {
				expect(() => validateVDOM({ tag: "div", children: ["Hello"] })).not.toThrow();
			});

			it("accepts nested valid VDOM", () => {
				expect(() =>
					validateVDOM({
						tag: "div",
						children: [{ tag: "span", children: ["Nested"] }, "Text", 42, null],
					}),
				).not.toThrow();
			});
		});

		describe("invalid VDOM", () => {
			it("rejects object without tag property", () => {
				expect(() => validateVDOM({ props: {} })).toThrow(InvalidVDOMError);
				expect(() => validateVDOM({ props: {} })).toThrow(
					'VDOM element must have a "tag" property',
				);
			});

			it("rejects object with non-string tag", () => {
				expect(() => validateVDOM({ tag: 123 })).toThrow(InvalidVDOMError);
				expect(() => validateVDOM({ tag: 123 })).toThrow('"tag" must be a string');
			});

			it("rejects object with null tag", () => {
				expect(() => validateVDOM({ tag: null })).toThrow(InvalidVDOMError);
				expect(() => validateVDOM({ tag: null })).toThrow('"tag" must be a string');
			});

			it("rejects object with non-array children", () => {
				expect(() => validateVDOM({ tag: "div", children: "not array" })).toThrow(InvalidVDOMError);
				expect(() => validateVDOM({ tag: "div", children: "not array" })).toThrow(
					'"children" must be an array',
				);
			});

			it("rejects nested invalid child", () => {
				expect(() =>
					validateVDOM({
						tag: "div",
						children: [{ props: {} }],
					}),
				).toThrow(InvalidVDOMError);
				expect(() =>
					validateVDOM({
						tag: "div",
						children: [{ props: {} }],
					}),
				).toThrow('VDOM element must have a "tag" property');
			});

			it("rejects deeply nested invalid child", () => {
				expect(() =>
					validateVDOM({
						tag: "div",
						children: [
							{
								tag: "section",
								children: [{ tag: "article", children: [{ invalid: true }] }],
							},
						],
					}),
				).toThrow(InvalidVDOMError);
			});

			it("rejects invalid type in array", () => {
				expect(() => validateVDOM([{ tag: "span" }, { invalid: true }])).toThrow(InvalidVDOMError);
			});

			it("reports correct message for invalid type", () => {
				// Functions are not valid VDOM
				expect(() => validateVDOM(() => {})).toThrow(InvalidVDOMError);
				expect(() => validateVDOM(() => {})).toThrow("Invalid VDOM type:");
			});
		});
	});

	describe("JSON parsing errors", () => {
		it("invalid JSON throws SyntaxError", () => {
			expect(() => JSON.parse("not valid json {")).toThrow(SyntaxError);
		});

		it("empty string throws SyntaxError", () => {
			expect(() => JSON.parse("")).toThrow(SyntaxError);
		});
	});
});
