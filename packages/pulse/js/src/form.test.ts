import { afterEach, beforeEach, describe, expect, it, vi } from "bun:test";
import { FormSubmissionError, submitForm } from "./form";

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
		globalThis.fetch = originalFetch;
		process.env.NODE_ENV = originalNodeEnv;
		vi.restoreAllMocks();
	});

	it("submits form data with fetch", async () => {
		const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
		globalThis.fetch = fetchMock as any;
		const event = makeSubmitEvent();
		const formData = new FormData();
		formData.set("name", "Ada");

		await submitForm({ event, action: "http://pulse.test/submit", formData });

		expect(event.preventDefault).toHaveBeenCalled();
		expect(fetchMock).toHaveBeenCalledWith(
			new URL("http://pulse.test/submit", window.location.href),
			expect.objectContaining({
				method: "POST",
				credentials: "include",
				body: formData,
			}),
		);
	});

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
