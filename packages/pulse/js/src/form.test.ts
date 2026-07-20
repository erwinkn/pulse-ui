import { afterEach, beforeEach, describe, expect, it, vi } from "bun:test";
import React from "react";
import { cleanup, render } from "@testing-library/react";
import { FormSubmissionError, PulseForm, submitForm } from "./form";
import { deserialize } from "./serialize/serializer";

const originalFetch = globalThis.fetch;
const originalNodeEnv = process.env.NODE_ENV;

function makeSubmitEvent() {
	const form = document.createElement("form");
	let prevented = false;
	return {
		currentTarget: form,
		nativeEvent: { submitter: null },
		get defaultPrevented() {
			return prevented;
		},
		preventDefault: vi.fn(() => {
			prevented = true;
		}),
	} as any;
}

describe("submitForm", () => {
	beforeEach(() => {
		process.env.NODE_ENV = "development";
	});

	afterEach(() => {
		cleanup();
		globalThis.fetch = originalFetch;
		process.env.NODE_ENV = originalNodeEnv;
		vi.restoreAllMocks();
	});

	it("preserves the form action", () => {
		const action = "/submit?source=form#done";
		const view = render(React.createElement(PulseForm, { action }));

		expect(view.container.querySelector("form")?.getAttribute("action")).toBe(action);
	});

	it("submits form data with fetch", async () => {
		const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
		globalThis.fetch = fetchMock as any;
		const event = makeSubmitEvent();
		const formData = new FormData();
		formData.set("name", "Ada");

		await submitForm({ event, action: "/submit", formData });

		expect(event.preventDefault).toHaveBeenCalled();
		expect(fetchMock).toHaveBeenCalledWith(
			"/submit",
			expect.objectContaining({
				method: "POST",
				credentials: "same-origin",
				body: formData,
			}),
		);
	});

	it("encodes structured values and files as Pulse multipart data", async () => {
		const fetchMock = vi.fn(
			async (_input: RequestInfo | URL, _init?: RequestInit) =>
				new Response(null, { status: 204 }),
		);
		globalThis.fetch = fetchMock as any;
		const file = new File(["contents"], "sample.txt", { type: "text/plain" });
		const values = {
			samples: [
				{
					sample_id: "sample-1",
					project: { metadata: { kind: "research" } },
					attachments: [file],
				},
			],
		};

		await submitForm({
			event: makeSubmitEvent(),
			action: "http://pulse.test/submit",
			values,
		});

		const body = fetchMock.mock.calls[0]![1]!.body as FormData;
		const serialized = JSON.parse(body.get("__pulse_data__") as string);
		expect(deserialize<any>(serialized)).toEqual({
			samples: [
				{
					sample_id: "sample-1",
					project: { metadata: { kind: "research" } },
					attachments: [null],
				},
			],
		});
		expect(JSON.parse(body.get("__pulse_files__") as string)).toEqual([
			{
				part: "__pulse_files__.0",
				path: ["samples", 0, "attachments", 0],
			},
		]);
		expect(body.get("__pulse_files__.0")).toBe(file);
		expect(Array.from(body.keys())).toEqual([
			"__pulse_data__",
			"__pulse_files__",
			"__pulse_files__.0",
		]);
	});

	it.each(["__pulse_data__", "__pulse_files__"])(
		"rejects the reserved structured form field %s",
		async (reserved) => {
			const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
			globalThis.fetch = fetchMock as any;

			await expect(
				submitForm({
					event: makeSubmitEvent(),
					action: "http://pulse.test/submit",
					values: { [reserved]: "user value" },
				}),
			).rejects.toThrow(`Form field '${reserved}' is reserved by Pulse`);
			expect(fetchMock).not.toHaveBeenCalled();
		},
	);

	it("rejects and logs when the server returns a non-2xx response", async () => {
		const fetchMock = vi.fn(
			async () =>
				new Response("database unavailable", {
					status: 500,
					statusText: "Internal Server Error",
				}),
		);
		globalThis.fetch = fetchMock as any;
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

		let error: unknown;
		try {
			await submitForm({
				event: makeSubmitEvent(),
				action: "http://pulse.test/submit",
				formData: new FormData(),
			});
		} catch (err) {
			error = err;
		}

		expect(error).toBeInstanceOf(FormSubmissionError);
		expect((error as FormSubmissionError).status).toBe(500);
		expect((error as FormSubmissionError).body).toBe("database unavailable");
		expect(consoleError).toHaveBeenCalledWith(
			"[Pulse] Form submission failed",
			error,
		);
	});

	it("does not submit when user onSubmit prevents default", async () => {
		const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
		globalThis.fetch = fetchMock as any;
		const event = makeSubmitEvent();

		await submitForm({
			event,
			action: "http://pulse.test/submit",
			onSubmit: (submitEvent) => submitEvent.preventDefault(),
		});

		expect(fetchMock).not.toHaveBeenCalled();
	});
});
