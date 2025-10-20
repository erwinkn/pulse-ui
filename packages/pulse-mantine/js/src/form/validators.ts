import type { FormValidateInput } from "@mantine/form";
import {
	hasLength as hasLengthValidator,
	isEmail,
	isInRange,
	isJSONString,
	isNotEmpty,
	isNotEmptyHTML,
	matchesField,
	matches as matchesValidator,
} from "@mantine/form";
import type { ReactNode } from "react";

type RecursiveRecord<T> = T | { [key: string]: RecursiveRecord<T> };
export type RuleFn = (value: any, values: any, path: string) => ReactNode;

export type ServerValidationRule = {
	debounceMs?: number;
	runOn?: "change" | "blur" | "submit";
};
export type ServerValidation = Partial<Record<string, ServerValidationRule[]>>;
export type ClientValidation = Partial<Record<string, RecursiveRecord<RuleFn>>>;

// Schema support: accept a normalized validator schema coming from Python,
// where each leaf is a validator spec or list of specs. We convert it to Mantine
// rules object of functions at runtime.
export type ValidatorSpec =
	| { $kind: "isNotEmpty"; error?: string }
	| { $kind: "isEmail"; error?: string }
	| {
			$kind: "matches";
			pattern: string;
			flags?: string | null;
			// Optional client-specific overrides to account for JS/Python regex differences
			clientPattern?: string | null;
			clientFlags?: string | null;
			error?: string;
	  }
	| { $kind: "isInRange"; min?: number; max?: number; error?: string }
	| {
			$kind: "hasLength";
			min?: number;
			max?: number;
			exact?: number;
			error?: string;
	  }
	| { $kind: "matchesField"; field: string; error?: string }
	| { $kind: "isJSONString"; error?: string }
	| { $kind: "isNotEmptyHTML"; error?: string }
	| {
			$kind: "isUrl";
			protocols?: string[] | null;
			requireProtocol?: boolean;
			error?: string;
	  }
	| { $kind: "isUUID"; version?: 1 | 2 | 3 | 4 | 5; error?: string }
	| { $kind: "isULID"; error?: string }
	| { $kind: "isNumber"; error?: string }
	| { $kind: "isInteger"; error?: string }
	| { $kind: "isDate"; error?: string }
	| { $kind: "isISODate"; withTime?: boolean; error?: string }
	| {
			$kind: "isBefore";
			field?: string;
			value?: any;
			inclusive?: boolean;
			error?: string;
	  }
	| {
			$kind: "isAfter";
			field?: string;
			value?: any;
			inclusive?: boolean;
			error?: string;
	  }
	| { $kind: "minItems"; count: number; error?: string }
	| { $kind: "maxItems"; count: number; error?: string }
	| { $kind: "isArrayNotEmpty"; error?: string }
	| {
			$kind: "allowedFileTypes";
			mimeTypes?: string[] | null;
			extensions?: string[] | null;
			error?: string;
	  }
	| { $kind: "maxFileSize"; bytes: number; error?: string }
	| {
			$kind: "requiredWhen";
			field: string;
			equals?: any;
			notEquals?: any;
			in?: any[] | null;
			notIn?: any[] | null;
			truthy?: boolean;
			error?: string;
	  }
	| {
			$kind: "requiredUnless";
			field: string;
			equals?: any;
			notEquals?: any;
			in?: any[] | null;
			notIn?: any[] | null;
			truthy?: boolean;
			error?: string;
	  }
	| {
			$kind: "startsWith";
			value: string;
			caseSensitive?: boolean;
			error?: string;
	  }
	| {
			$kind: "endsWith";
			value: string;
			caseSensitive?: boolean;
			error?: string;
	  }
	| {
			$kind: "server";
			debounceMs?: number;
			runOn?: "change" | "blur" | "submit";
	  };

export type ValidatorSchema = {
	[key: string]: ValidatorSchema | ValidatorSpec[] | ValidatorSpec;
};

function isValidatorSpecArray(x: any): x is ValidatorSpec[] {
	return Array.isArray(x) && x.every((i) => i && typeof i === "object" && "$kind" in i);
}
function isValidatorSpec(x: any): x is ValidatorSpec {
	return x && typeof x === "object" && !Array.isArray(x) && "$kind" in x;
}

export function isValidatorSchema(x: any): x is ValidatorSchema {
	if (!x || typeof x !== "object" || Array.isArray(x)) return false;
	return Object.values(x).some(
		(v) => isValidatorSpec(v) || isValidatorSpecArray(v) || (v && typeof v === "object"),
	);
}

function isEmptyValue(value: any): boolean {
	if (value === null || value === undefined) return true;
	if (typeof value === "string") return value.trim().length === 0;
	if (Array.isArray(value)) return value.length === 0;
	if (typeof FileList !== "undefined" && value instanceof FileList) {
		return value.length === 0;
	}
	return false;
}

function getValueAtPath(source: any, path?: string): any {
	if (!source || !path) return undefined;
	return path
		.split(".")
		.reduce((acc: any, key: string) => (acc == null ? undefined : acc[key]), source);
}

function coerceNumber(value: any): number | null {
	if (typeof value === "number") {
		return Number.isFinite(value) ? value : null;
	}
	if (typeof value === "string") {
		const trimmed = value.trim();
		if (trimmed.length === 0) return null;
		const num = Number(trimmed);
		return Number.isFinite(num) ? num : null;
	}
	if (value instanceof Number) {
		const num = Number(value.valueOf());
		return Number.isFinite(num) ? num : null;
	}
	return null;
}

function coerceComparable(value: any): number | null {
	if (value instanceof Date) {
		const ts = value.getTime();
		return Number.isNaN(ts) ? null : ts;
	}
	if (typeof value === "number") {
		return Number.isFinite(value) ? value : null;
	}
	if (typeof value === "string") {
		const trimmed = value.trim();
		if (trimmed.length === 0) return null;
		const numeric = Number(trimmed);
		if (Number.isFinite(numeric)) return numeric;
		const parsed = Date.parse(trimmed);
		return Number.isNaN(parsed) ? null : parsed;
	}
	if (value instanceof Number) {
		const num = Number(value.valueOf());
		return Number.isFinite(num) ? num : null;
	}
	return null;
}

function coerceDate(value: any): number | null {
	if (value instanceof Date) {
		const ts = value.getTime();
		return Number.isNaN(ts) ? null : ts;
	}
	if (typeof value === "string") {
		const trimmed = value.trim();
		if (trimmed.length === 0) return null;
		const parsed = Date.parse(trimmed);
		return Number.isNaN(parsed) ? null : parsed;
	}
	if (typeof value === "number") {
		return Number.isFinite(value) ? value : null;
	}
	if (value instanceof Number) {
		const num = Number(value.valueOf());
		return Number.isFinite(num) ? num : null;
	}
	return null;
}

function toFileArray(value: any): File[] {
	if (typeof File === "undefined") return [];
	if (!value) return [];
	if (value instanceof File) return [value];
	if (typeof FileList !== "undefined" && value instanceof FileList) {
		return Array.from(value);
	}
	if (Array.isArray(value)) {
		return value.filter((item: any): item is File => item instanceof File);
	}
	return [];
}

type ConditionSpec = {
	equals?: any;
	notEquals?: any;
	in?: any[] | null;
	notIn?: any[] | null;
	truthy?: boolean;
};

function evaluateCondition(value: any, spec: ConditionSpec): boolean {
	let result = true;
	if ("equals" in spec) {
		result &&= value === spec.equals;
	}
	if ("notEquals" in spec) {
		result &&= value !== spec.notEquals;
	}
	if (spec.in) {
		result &&= spec.in.some((item) => item === value);
	}
	if (spec.notIn) {
		result &&= !spec.notIn.some((item) => item === value);
	}
	if ("truthy" in spec) {
		result &&= Boolean(value) === Boolean(spec.truthy);
	} else if (!("equals" in spec) && !("notEquals" in spec) && !spec.in && !spec.notIn) {
		result &&= Boolean(value);
	}
	return result;
}

function formatError(error: string | undefined, fallback: string): string {
	return error ?? fallback;
}

// Compose multiple built-in validators (client-only)
export function composeClientSpecs(specs: ValidatorSpec[]): RuleFn {
	const validators: RuleFn[] = specs
		.filter((s) => s.$kind !== "server")
		.map((spec) => {
			switch (spec.$kind) {
				case "isNotEmpty":
					return isNotEmpty(spec.error);
				case "isEmail":
					return isEmail(spec.error);
				case "matches": {
					const pattern = spec.clientPattern ?? spec.pattern;
					const flags = spec.clientFlags ?? spec.flags ?? undefined;
					const re = new RegExp(pattern, flags);
					return matchesValidator(re, spec.error);
				}
				case "isInRange": {
					const opts = { min: spec.min, max: spec.max };
					return isInRange(opts, spec.error);
				}
				case "hasLength": {
					if (typeof spec.exact === "number") {
						return hasLengthValidator(spec.exact, spec.error);
					}
					const opts = { min: spec.min, max: spec.max };
					return hasLengthValidator(opts, spec.error);
				}
				case "matchesField":
					return matchesField(spec.field, spec.error);
				case "isJSONString":
					return isJSONString(spec.error);
				case "isNotEmptyHTML":
					return isNotEmptyHTML(spec.error);
				case "isUrl":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const input = String(value).trim();
						const hasProtocol = /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(input);
						try {
							const url = hasProtocol ? new URL(input) : new URL(`https://${input}`);
							if (spec.requireProtocol && !hasProtocol) {
								return formatError(spec.error, "URL must include a protocol");
							}
							if (spec.protocols && spec.protocols.length > 0) {
								const allowed = spec.protocols
									.filter(Boolean)
									.map((p) => p.replace(/:$/, "").toLowerCase());
								if (allowed.length > 0) {
									const protocol = url.protocol.replace(/:$/, "").toLowerCase();
									if (!allowed.includes(protocol)) {
										const list = allowed.join(", ");
										return formatError(
											spec.error,
											`URL must use protocol${allowed.length > 1 ? "s" : ""}: ${list}`,
										);
									}
								}
							}
							return null;
						} catch (_err) {
							return formatError(spec.error, "Must be a valid URL");
						}
					};
				case "isUUID":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const str = String(value).trim();
						const version = spec.version;
						const uuidPattern = version
							? new RegExp(
									`^[0-9a-f]{8}-[0-9a-f]{4}-${version}[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`,
									"i",
								)
							: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
						if (!uuidPattern.test(str)) {
							return formatError(
								spec.error,
								version ? `Must be a valid UUID v${version}` : "Must be a valid UUID",
							);
						}
						return null;
					};
				case "isULID":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const str = String(value).trim().toUpperCase();
						const ulidPattern = /^[0-9A-HJKMNP-TV-Z]{26}$/;
						if (!ulidPattern.test(str)) {
							return formatError(spec.error, "Must be a valid ULID");
						}
						return null;
					};
				case "isNumber":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const num = coerceNumber(value);
						if (num === null) {
							return formatError(spec.error, "Must be a number");
						}
						return null;
					};
				case "isInteger":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const num = coerceNumber(value);
						if (num === null || !Number.isInteger(num)) {
							return formatError(spec.error, "Must be an integer");
						}
						return null;
					};
				case "isDate":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const timestamp = coerceDate(value);
						if (timestamp === null) {
							return formatError(spec.error, "Must be a valid date");
						}
						return null;
					};
				case "isISODate":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						if (value instanceof Date) return null;
						const str = String(value).trim();
						const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
						const dateTimeRegex =
							/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(Z|[+-]\d{2}:\d{2})?$/;
						const matches = spec.withTime ? dateTimeRegex.test(str) : dateRegex.test(str);
						if (!matches) {
							return formatError(
								spec.error,
								spec.withTime ? "Must be an ISO-8601 datetime" : "Must be an ISO-8601 date",
							);
						}
						return null;
					};
				case "isBefore":
					return (value: any, values: any) => {
						const other =
							spec.field !== undefined ? getValueAtPath(values, spec.field) : spec.value;
						const left = coerceComparable(value);
						const right = coerceComparable(other);
						if (left === null || right === null) return null;
						const ok = spec.inclusive ? left <= right : left < right;
						if (!ok) {
							return formatError(spec.error, "Value must be before target");
						}
						return null;
					};
				case "isAfter":
					return (value: any, values: any) => {
						const other =
							spec.field !== undefined ? getValueAtPath(values, spec.field) : spec.value;
						const left = coerceComparable(value);
						const right = coerceComparable(other);
						if (left === null || right === null) return null;
						const ok = spec.inclusive ? left >= right : left > right;
						if (!ok) {
							return formatError(spec.error, "Value must be after target");
						}
						return null;
					};
				case "minItems":
					return (value: any) => {
						const arr = Array.isArray(value)
							? value
							: typeof FileList !== "undefined" && value instanceof FileList
								? Array.from(value)
								: null;
						const length = arr ? arr.length : value == null ? 0 : NaN;
						if (!arr || Number.isNaN(length) || length < spec.count) {
							return formatError(
								spec.error,
								spec.count === 1
									? "Select at least one item"
									: `Select at least ${spec.count} items`,
							);
						}
						return null;
					};
				case "maxItems":
					return (value: any) => {
						if (value == null) return null;
						const arr = Array.isArray(value)
							? value
							: typeof FileList !== "undefined" && value instanceof FileList
								? Array.from(value)
								: null;
						if (!arr) {
							return formatError(spec.error, "Value must be a list");
						}
						if (arr.length > spec.count) {
							return formatError(
								spec.error,
								`Select no more than ${spec.count} item${spec.count === 1 ? "" : "s"}`,
							);
						}
						return null;
					};
				case "isArrayNotEmpty":
					return (value: any) => {
						const length = Array.isArray(value)
							? value.length
							: typeof FileList !== "undefined" && value instanceof FileList
								? value.length
								: 0;
						if (length === 0) {
							return formatError(spec.error, "At least one item is required");
						}
						return null;
					};
				case "allowedFileTypes":
					return (value: any) => {
						const files = toFileArray(value);
						if (files.length === 0) return null;
						const mimeRules = (spec.mimeTypes ?? []).filter(Boolean).map((m) => m.toLowerCase());
						const extRules = (spec.extensions ?? [])
							.filter(Boolean)
							.map((ext) => ext.replace(/^\./, "").toLowerCase());
						for (const file of files) {
							const mime = (file.type || "").toLowerCase();
							if (mimeRules.length > 0) {
								const matchesMime = mimeRules.some((rule) => {
									if (rule.endsWith("/*")) {
										const prefix = rule.slice(0, -1);
										return mime.startsWith(prefix);
									}
									return mime === rule;
								});
								if (!matchesMime) {
									return formatError(spec.error, "File type is not allowed");
								}
							}
							if (extRules.length > 0) {
								const name = file.name || "";
								const ext = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
								if (!extRules.includes(ext)) {
									return formatError(spec.error, "File extension is not allowed");
								}
							}
						}
					};
				case "maxFileSize":
					return (value: any) => {
						const files = toFileArray(value);
						for (const file of files) {
							if (file.size > spec.bytes) {
								return formatError(spec.error, "File is too large");
							}
						}
					};
				case "requiredWhen":
					return (value: any, values: any) => {
						const other = getValueAtPath(values, spec.field);
						if (!evaluateCondition(other, spec)) return null;
						if (isEmptyValue(value)) {
							return formatError(spec.error, "This field is required");
						}
					};
				case "requiredUnless":
					return (value: any, values: any) => {
						const other = getValueAtPath(values, spec.field);
						if (evaluateCondition(other, spec)) return null;
						if (isEmptyValue(value)) {
							return formatError(spec.error, "This field is required");
						}
					};
				case "startsWith":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const subject = String(value);
						const target = spec.value;
						if (spec.caseSensitive === false) {
							if (!subject.toLowerCase().startsWith(target.toLowerCase())) {
								return formatError(spec.error, `Must start with ${target}`);
							}
						} else if (!subject.startsWith(target)) {
							return formatError(spec.error, `Must start with ${target}`);
						}
					};
				case "endsWith":
					return (value: any) => {
						if (isEmptyValue(value)) return null;
						const subject = String(value);
						const target = spec.value;
						if (spec.caseSensitive === false) {
							if (!subject.toLowerCase().endsWith(target.toLowerCase())) {
								return formatError(spec.error, `Must end with ${target}`);
							}
						} else if (!subject.endsWith(target)) {
							return formatError(spec.error, `Must end with ${target}`);
						}
					};
				// server rules are handled via centralized event routing in Form.tsx
				default:
					return () => null;
			}
		});

	return (value: any, values: any, path: string) => {
		for (const v of validators) {
			const res = v(value, values, path);
			if (res) return res;
		}
		return null;
	};
}

export function splitValidationSchema(schema: ValidatorSchema): {
	clientRules: FormValidateInput<any>;
	serverRulesByPath: ServerValidation;
} {
	const serverRulesByPath: ServerValidation = {};
	const join = (p: string, k: string) => (p ? `${p}.${k}` : k);

	const ensure = (path: string) => {
		if (!serverRulesByPath[path]) serverRulesByPath[path] = [];
		return serverRulesByPath[path];
	};

	const walk = (node: ValidatorSchema | ValidatorSpec[] | ValidatorSpec, path: string) => {
		if (Array.isArray(node)) {
			// Collect server validators for this path
			for (const spec of node) {
				if (isValidatorSpec(spec) && spec.$kind === "server") {
					ensure(path).push({ debounceMs: spec.debounceMs, runOn: spec.runOn });
				}
			}
			// Build client rule excluding server items
			return composeClientSpecs(node);
		}
		if (isValidatorSpec(node)) {
			if (node.$kind === "server") {
				ensure(path).push({ debounceMs: node.debounceMs, runOn: node.runOn });
			}
			return composeClientSpecs([node]);
		}
		const out: Record<string, RecursiveRecord<RuleFn>> = {};
		for (const [k, v] of Object.entries(node)) {
			out[k] = walk(v, join(path, k));
		}
		return out;
	};

	const clientRules = walk(schema, "") as FormValidateInput<any>;
	return { clientRules, serverRulesByPath };
}
