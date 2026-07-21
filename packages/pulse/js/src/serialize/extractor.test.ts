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
});
