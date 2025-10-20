import { describe, expect, it } from "bun:test";
import { composeClientSpecs, splitValidationSchema, type ValidatorSpec } from "./validators";

function ruleFrom(spec: ValidatorSpec) {
	return composeClientSpecs([spec]);
}

describe("validators: URL", () => {
	it("validates protocol requirements and allowed protocols", () => {
		// basic URL without protocol allowed
		const url1 = ruleFrom({ $kind: "isUrl", error: "e" });
		expect(url1("example.com", { field: "example.com" }, "field")).toBeNull();

		// require protocol
		const url2 = ruleFrom({
			$kind: "isUrl",
			requireProtocol: true,
			error: "e",
		});
		expect(url2("example.com", { field: "example.com" }, "field")).toBe("e");

		// allowed protocols list
		const url3 = ruleFrom({ $kind: "isUrl", protocols: ["https"], error: "e" });
		expect(url3("http://example.com", {}, "f")).toBe("e");
		const url4 = ruleFrom({
			$kind: "isUrl",
			protocols: ["http", "https"],
			error: "e",
		});
		expect(url4("https://example.com", {}, "f")).toBeNull();
	});
});

describe("validators: UUID/ULID", () => {
	it("validates UUID (v4) and ULID", () => {
		const uuid4 = ruleFrom({ $kind: "isUUID", version: 4, error: "e" });
		expect(uuid4("not-uuid", {}, "f")).toBe("e");
		expect(uuid4("8c1d0b04-7f9b-4f75-9d3c-6b0b8ee7c7c1", {}, "f")).toBeNull();

		const ulid = ruleFrom({ $kind: "isULID", error: "e" });
		expect(ulid("not-ulid", {}, "f")).toBe("e");
		expect(ulid("01HAF8ZJ2R9T5S8Q2YKD3B4N5M", {}, "f")).toBeNull();
	});
});

describe("validators: ISO date", () => {
	it("checks date and datetime variants", () => {
		const onlyDate = ruleFrom({
			$kind: "isISODate",
			withTime: false,
			error: "e",
		});
		expect(onlyDate("2024-01-01", {}, "f")).toBeNull();
		expect(onlyDate("2024-01-01T10:20:30Z", {}, "f")).toBe("e");

		const withTime = ruleFrom({
			$kind: "isISODate",
			withTime: true,
			error: "e",
		});
		expect(withTime("2024-01-01T10:20:30Z", {}, "f")).toBeNull();
	});
});

describe("validators: before/after comparisons", () => {
	it("compares using other field and inclusive flag", () => {
		const values = { start: "2024-01-01", end: "2024-01-02" };
		const isBefore = ruleFrom({
			$kind: "isBefore",
			field: "end",
			inclusive: true,
			error: "e",
		});
		const isAfter = ruleFrom({
			$kind: "isAfter",
			field: "start",
			inclusive: true,
			error: "e",
		});
		expect(isBefore(values.start, values, "start")).toBeNull();
		expect(isAfter(values.end, values, "end")).toBeNull();

		const beforeFail = ruleFrom({
			$kind: "isBefore",
			field: "start",
			error: "e",
		});
		expect(beforeFail(values.end, values, "end")).toBe("e");
		const afterFail = ruleFrom({ $kind: "isAfter", field: "end", error: "e" });
		expect(afterFail(values.start, values, "start")).toBe("e");
	});
});

describe("validators: file validators", () => {
	it("validates allowed mime types and extensions", () => {
		const file = new File([new Uint8Array(1024)], "a.png", {
			type: "image/png",
		});
		const typesOk = ruleFrom({
			$kind: "allowedFileTypes",
			mimeTypes: ["image/*"],
			error: "e",
		});
		const extOk = ruleFrom({
			$kind: "allowedFileTypes",
			extensions: ["png"],
			error: "e",
		});
		const extBad = ruleFrom({
			$kind: "allowedFileTypes",
			extensions: ["jpg"],
			error: "e",
		});

		expect(typesOk([file], {}, "f")).toBeNull();
		expect(extOk([file], {}, "f")).toBeNull();
		expect(extBad([file], {}, "f")).toBe("e");
	});

	it("validates maximum file size", () => {
		const big = new File([new Uint8Array(10 * 1024 * 1024)], "b.bin", {
			type: "application/octet-stream",
		});
		const max = ruleFrom({
			$kind: "maxFileSize",
			bytes: 5 * 1024 * 1024,
			error: "e",
		});
		expect(max([big], {}, "f")).toBe("e");
	});
});

describe("validators: list/array validators", () => {
	it("checks min/max items and non-empty arrays", () => {
		const min1 = ruleFrom({ $kind: "minItems", count: 1, error: "e" });
		const max1 = ruleFrom({ $kind: "maxItems", count: 1, error: "e" });
		const notEmpty = ruleFrom({ $kind: "isArrayNotEmpty", error: "e" });

		expect(min1([], {}, "f")).toBe("e");
		expect(min1([1], {}, "f")).toBeNull();
		expect(max1([1, 2], {}, "f")).toBe("e");
		expect(notEmpty([1], {}, "f")).toBeNull();
	});
});

describe("validators: conditional required", () => {
	it("requiredWhen and requiredUnless", () => {
		const reqWhen = ruleFrom({
			$kind: "requiredWhen",
			field: "flag",
			truthy: true,
			error: "e",
		});
		const values1 = { flag: true, x: "" } as any;
		expect(reqWhen(values1.x, values1, "x")).toBe("e");

		const reqUnless = ruleFrom({
			$kind: "requiredUnless",
			field: "flag",
			truthy: true,
			error: "e",
		});
		const values2 = { flag: false, x: "" } as any;
		expect(reqUnless(values2.x, values2, "x")).toBe("e");
	});
});

describe("validators: string boundaries", () => {
	it("startsWith/endsWith with case-insensitivity", () => {
		const sw = ruleFrom({ $kind: "startsWith", value: "AA", error: "e" });
		const swnc = ruleFrom({
			$kind: "startsWith",
			value: "AA",
			caseSensitive: false,
			error: "e",
		});
		const ew = ruleFrom({ $kind: "endsWith", value: "BB", error: "e" });
		const ewnc = ruleFrom({
			$kind: "endsWith",
			value: "BB",
			caseSensitive: false,
			error: "e",
		});

		expect(sw("AABB", {}, "f")).toBeNull();
		expect(swnc("aabb", {}, "f")).toBeNull();
		expect(ew("AABB", {}, "f")).toBeNull();
		expect(ewnc("aabb", {}, "f")).toBeNull();
		expect(sw("XXBB", {}, "f")).toBe("e");
		expect(ew("AAXX", {}, "f")).toBe("e");
	});
});

describe("validators: client/server regex overrides", () => {
	it("uses clientPattern/clientFlags when provided", () => {
		const spec: ValidatorSpec = {
			$kind: "matches",
			pattern: "^[a-z]+$",
			clientPattern: "^[a-z]+$",
			clientFlags: "i",
			error: "e",
		};
		const rule = composeClientSpecs([spec]);
		expect(rule("ABC", { field: "ABC" }, "field")).toBeNull();
	});

	it("falls back to server pattern/flags when client overrides are absent", () => {
		const spec: ValidatorSpec = {
			$kind: "matches",
			pattern: "^[a-z]+$",
			error: "e",
		};
		const rule = composeClientSpecs([spec]);
		expect(rule("ABC", { field: "ABC" }, "field")).toBe("e");
		expect(rule("abc", { field: "abc" }, "field")).toBeNull();
	});
});

describe("validators: splitValidationSchema", () => {
	it("collects server rules and builds client rules from specs", () => {
		const schema = {
			fieldA: [
				{ $kind: "isNotEmpty", error: "req" },
				{ $kind: "server", debounceMs: 150 },
			],
			nested: {
				inner: {
					$kind: "matches",
					pattern: "^[a-z]+$",
					clientPattern: "^[a-z]+$",
					clientFlags: "i",
					error: "e",
				} as ValidatorSpec,
			},
		} as const;

		const { clientRules, serverRulesByPath } = splitValidationSchema(schema as any);
		expect(serverRulesByPath.fieldA).toEqual([{ debounceMs: 150 }]);
		const nestedRule = (clientRules as any).nested.inner as (
			value: any,
			values: any,
			path: string,
		) => void;
		expect(nestedRule("ABC", { nested: { inner: "ABC" } }, "nested.inner")).toBeNull();
	});
});
