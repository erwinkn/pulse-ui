import { type ComponentPropsWithoutRef, type FormEvent, forwardRef, useCallback } from "react";

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

interface SubmitForm {
	event: FormEvent<HTMLFormElement>;
	action: string;
	onSubmit?: PulseFormProps["onSubmit"];
	formData?: FormData;
	force?: boolean;
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

export async function submitForm({ event, action, onSubmit, formData, force }: SubmitForm) {
	onSubmit?.(event);
	if (!force && event.defaultPrevented) {
		return;
	}
	const form = event.currentTarget;
	event.preventDefault();
	const nativeEvent = event.nativeEvent as SubmitEvent;
	if (!formData) {
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
