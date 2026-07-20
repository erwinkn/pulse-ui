import { describe, expect, it } from "bun:test";
import { render } from "@testing-library/react";
import React from "react";
import { extractEvent } from "./events";
import { serialize } from "./serializer";

describe("form event extraction", () => {
	it("does not let named controls shadow form properties", () => {
		const form = document.createElement("form");
		form.id = "profile-form";
		form.name = "profile";
		form.action = "/submit";
		form.method = "post";
		form.target = "_blank";

		for (const property of [
			"id",
			"name",
			"action",
			"method",
			"target",
			"tagName",
			"accessKeyLabel",
		]) {
			const control = document.createElement("input");
			control.name = property;
			Object.defineProperty(form, property, {
				configurable: true,
				value: control,
			});
			form.append(control);
		}

		const extracted = extractEvent({
			type: "submit",
			target: form,
			nativeEvent: {},
			isDefaultPrevented: () => false,
		});

		expect(extracted.target).toMatchObject({
			id: "profile-form",
			name: "profile",
			method: "post",
			target: "_blank",
			tagName: "form",
		});
		expect(typeof extracted.target.action).toBe("string");
		expect(extracted.target.id).not.toBe(controlFor(form, "id"));
		expect(extracted.target.name).not.toBe(controlFor(form, "name"));
		expect(extracted.target.action).not.toBe(controlFor(form, "action"));
		expect(extracted.target.method).not.toBe(controlFor(form, "method"));
		expect(extracted.target.target).not.toBe(controlFor(form, "target"));
		expect(extracted.target.tagName).not.toBe(controlFor(form, "tagName"));
		expect(extracted.target.accessKeyLabel).toBeUndefined();
		expect(extracted.target.accessKeyLabel).not.toBe(controlFor(form, "accessKeyLabel"));

		expect(serialize(extracted)).toMatchObject([
			5,
			{
				target: {
				id: "profile-form",
				name: "profile",
				method: "post",
				target: "_blank",
				tagName: "form",
				},
			},
		]);
	});

	it("does not traverse React internals on a large form", () => {
		const view = render(
			React.createElement(
				"form",
				{ name: "profile" },
				React.createElement("input", { name: "name", defaultValue: "qgis" }),
				...Array.from({ length: 3000 }, (_, index) =>
					React.createElement("span", { key: index }, index),
				),
			),
		);
		const form = view.container.querySelector("form")!;
		const control = controlFor(form, "name");

		// happy-dom gives IDL properties precedence over named controls, unlike browsers.
		// Simulate the browser's named-property result on a real React-mounted DOM tree.
		expect(Object.keys(control).some((key) => key.startsWith("__reactFiber$"))).toBe(true);
		Object.defineProperty(form, "name", {
			configurable: true,
			value: control,
		});

		const extracted = extractEvent({
			type: "submit",
			target: form,
			nativeEvent: {},
			isDefaultPrevented: () => false,
		});

		expect(extracted.target.name).toBe("profile");
		expect(() => serialize(extracted)).not.toThrow();
	});
});

describe("extractEvent", () => {
	it("normalizes non-finite DOM values at extraction", () => {
		const event = {
			nativeEvent: {},
			isDefaultPrevented: () => false,
			type: "click",
			target: document.createElement("button"),
			relatedTarget: null,
			// The DOM legitimately produces non-finite numbers (e.g. a live
			// stream's media duration is Infinity); the serializer rejects
			// Infinity, so the extractor must normalize them to null.
			timeStamp: Number.POSITIVE_INFINITY,
			clientX: Number.NaN,
		};

		const extracted = extractEvent(event);
		const wire = serialize(extracted);

		expect(extracted.clientX).toBeNull();
		expect(extracted.timeStamp).toBeNull();
		expect(Object.hasOwn(extracted, "screenX")).toBe(false);
		expect(wire).toMatchObject([5, { clientX: null, timeStamp: null }]);
		expect("screenX" in (wire[1] as object)).toBe(false);
	});
});

function controlFor(form: HTMLFormElement, name: string): HTMLInputElement {
	return form.querySelector(`input[name="${name}"]`)!;
}
