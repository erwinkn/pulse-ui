import { describe, expect, it } from "bun:test";
import { createExtractor } from "./extractor";

describe("createExtractor", () => {
	it("omits undefined properties before serialization", () => {
		const extract = createExtractor<{ present: string; missing?: string }>()([
			"present",
			"missing",
		]);

		expect(extract({ present: "value", missing: undefined }) as object).toEqual({
			present: "value",
		});
	});

	it("normalizes non-finite DOM numbers to null", () => {
		const extract = createExtractor<{ finite: number; nan: number; infinite: number }>()(
			["finite", "nan", "infinite"],
			{ computed: () => Number.NEGATIVE_INFINITY },
		);

		expect(
			extract({ finite: 1, nan: Number.NaN, infinite: Number.POSITIVE_INFINITY }) as object,
		).toEqual(
			{
				finite: 1,
				nan: null,
				infinite: null,
				computed: null,
			},
		);
	});

	it("normalizes list-like host objects (e.g. DOMTokenList) to arrays", () => {
		class FakeTokenList {
			length = 2;
			0 = "btn";
			1 = "active";
		}
		const extract = createExtractor<{ classList: unknown }>()(["classList"]);

		expect(extract({ classList: new FakeTokenList() }) as object).toEqual({
			classList: ["btn", "active"],
		});
	});

	it("stringifies non-list-like host objects instead of throwing", () => {
		class FakeHostObject {
			toString() {
				return "host-object";
			}
		}
		const extract = createExtractor<{ value: unknown }>()(["value"]);

		expect(extract({ value: new FakeHostObject() }) as object).toEqual({
			value: "host-object",
		});
	});
});
