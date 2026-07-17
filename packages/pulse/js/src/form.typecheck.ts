import type { FormEvent } from "react";
import { submitForm } from "./form";

declare const event: FormEvent<HTMLFormElement>;

submitForm({ event, action: "/submit" });
submitForm({ event, action: "/submit", formData: new FormData() });
submitForm({ event, action: "/submit", values: { samples: [] } });

// @ts-expect-error formData and values are mutually exclusive
submitForm({
	event,
	action: "/submit",
	formData: new FormData(),
	values: { samples: [] },
});
