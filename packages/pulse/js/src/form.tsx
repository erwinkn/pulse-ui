import { type ComponentPropsWithoutRef, type FormEvent, forwardRef, useCallback } from "react";
import { serialize } from "./serialize/serializer";

const PULSE_DATA_FIELD = "__pulse_data__";
const PULSE_FILES_FIELD = "__pulse_files__";
const PULSE_FILE_PART_PREFIX = `${PULSE_FILES_FIELD}.`;

type FormPathSegment = string | number;

type FileManifestEntry = {
	part: string;
	path: FormPathSegment[];
};

export type PulseFormProps = ComponentPropsWithoutRef<"form"> & {
	action: string;
};

/**
 * PulseForm intercepts native form submissions and sends them through fetch so the
 * surrounding Pulse view stays mounted. Server-side handlers are still invoked via
 * the form action endpoint and reactive updates propagate over the socket.
 */
export const PulseForm = forwardRef<HTMLFormElement, PulseFormProps>(function PulseForm(
	{ onSubmit, action, ...rest },
	ref,
) {
	return (
		<form
			{...rest}
			action={action}
			ref={ref}
			onSubmit={useCallback(
				(event: FormEvent<HTMLFormElement>) => submitForm({ event, action, onSubmit }),
				[action, onSubmit],
			)}
		/>
	);
});

interface SubmitFormBase {
	event: FormEvent<HTMLFormElement>;
	action: string;
	onSubmit?: PulseFormProps["onSubmit"];
	force?: boolean;
}

type SubmitForm = SubmitFormBase &
	(
		| { formData: FormData; values?: never }
		| { values: unknown; formData?: never }
		| { formData?: never; values?: never }
	);

function containsFile(value: unknown, seen = new WeakSet<object>()): boolean {
	if (typeof File !== "undefined" && value instanceof File) return true;
	if (typeof FileList !== "undefined" && value instanceof FileList) {
		return value.length > 0;
	}
	if (value === null || typeof value !== "object") return false;
	if (seen.has(value)) return false;
	seen.add(value);
	if (value instanceof Map) {
		return Array.from(value.values()).some((item) => containsFile(item, seen));
	}
	if (value instanceof Set || Array.isArray(value)) {
		return Array.from(value).some((item) => containsFile(item, seen));
	}
	return Object.values(value).some((item) => containsFile(item, seen));
}

function encodeStructuredFormData(values: unknown): FormData {
	if (values === null || typeof values !== "object" || Array.isArray(values)) {
		throw new TypeError("Pulse structured form values must be an object");
	}
	for (const key of [PULSE_DATA_FIELD, PULSE_FILES_FIELD]) {
		if (Object.hasOwn(values, key)) {
			throw new Error(`Form field '${key}' is reserved by Pulse`);
		}
	}

	const files: Array<FileManifestEntry & { file: File }> = [];
	const clones = new WeakMap<object, unknown>();

	function visit(value: unknown, path: FormPathSegment[]): unknown {
		if (typeof File !== "undefined" && value instanceof File) {
			const part = `${PULSE_FILE_PART_PREFIX}${files.length}`;
			files.push({ part, path, file: value });
			return null;
		}
		if (typeof FileList !== "undefined" && value instanceof FileList) {
			return Array.from(value, (file, index) => visit(file, [...path, index]));
		}
		if (value === null || typeof value !== "object" || value instanceof Date) {
			return value;
		}
		if (value instanceof Set) {
			if (containsFile(value)) {
				throw new TypeError("Files inside Set form values are not supported");
			}
			return value;
		}

		const existing = clones.get(value);
		if (existing !== undefined) return existing;

		if (value instanceof Map) {
			const result = new Map<unknown, unknown>();
			clones.set(value, result);
			for (const [key, item] of value) {
				result.set(key, visit(item, [...path, String(key)]));
			}
			return result;
		}
		if (Array.isArray(value)) {
			const result: unknown[] = [];
			clones.set(value, result);
			for (let index = 0; index < value.length; index++) {
				result.push(visit(value[index], [...path, index]));
			}
			return result;
		}

		const result: Record<string, unknown> = {};
		clones.set(value, result);
		for (const [key, item] of Object.entries(value)) {
			result[key] = visit(item, [...path, key]);
		}
		return result;
	}

	const dataWithoutFiles = visit(values, []);
	const manifest = files.map(({ part, path }) => ({ part, path }));
	const formData = new FormData();
	formData.set(PULSE_DATA_FIELD, JSON.stringify(serialize(dataWithoutFiles)));
	formData.set(PULSE_FILES_FIELD, JSON.stringify(manifest));
	for (const { part, file } of files) {
		formData.append(part, file);
	}
	return formData;
}

export class FormSubmissionError extends Error {
	status: number;
	statusText: string;
	body: string;
	response: Response;

	constructor(response: Response, body: string) {
		const statusText = response.statusText ? ` ${response.statusText}` : "";
		super(`Form submission failed with HTTP ${response.status}${statusText}`);
		this.name = "FormSubmissionError";
		this.status = response.status;
		this.statusText = response.statusText;
		this.body = body;
		this.response = response;
	}
}

export async function submitForm(options: SubmitForm) {
	const { event, action, onSubmit, force } = options;
	let { formData } = options;
	onSubmit?.(event);
	if (!force && event.defaultPrevented) {
		return;
	}
	const form = event.currentTarget;
	event.preventDefault();
	const nativeEvent = event.nativeEvent as SubmitEvent;
	if (formData && "values" in options) {
		throw new Error("Provide either formData or values, not both");
	}
	if ("values" in options) {
		formData = encodeStructuredFormData(options.values);
	} else if (!formData) {
		formData = new FormData(form, nativeEvent.submitter);
	}
	const url = new URL(action, window.location.href);
	try {
		const response = await fetch(url, {
			method: "POST",
			// Required for our hosting scenarios of same host + different ports or 2 subdomains
			credentials: "include",
			body: formData,
		});
		if (!response.ok) {
			let body = "";
			try {
				body = await response.text();
			} catch {}
			throw new FormSubmissionError(response, body);
		}
	} catch (err) {
		if (process.env.NODE_ENV !== "production") {
			console.error("[Pulse] Form submission failed", err);
		}
		throw err;
	}
}
