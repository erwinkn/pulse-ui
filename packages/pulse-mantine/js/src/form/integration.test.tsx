import { describe, expect, it, mock } from "bun:test";
import { MantineProvider } from "@mantine/core";
import { fireEvent, render } from "@testing-library/react";
import { Checkbox, CheckboxGroup, MultiSelect, TagsInput } from "./fields";

const channel = {
	on: () => () => {},
	emit: mock(),
};
const client = {
	acquireChannel: () => channel,
	releaseChannel: () => {},
};
const submitForm = mock((_options: { formData: FormData }) => {});

mock.module("pulse-ui-client", () => ({
	serialize: (value: unknown) => value,
	submitForm,
	usePulseClient: () => client,
}));

const { Form } = await import("./form");

const listFields = [
	["MultiSelect", MultiSelect],
	["TagsInput", TagsInput],
] as const;

function submittedValues() {
	const formData = submitForm.mock.calls.at(-1)?.[0]?.formData;
	return JSON.parse(formData!.get("__data__") as string);
}

describe("MantineForm list-valued fields", () => {
	it.each(listFields)("submits %s values as a list", (_label, Field) => {
		submitForm.mockClear();
		channel.emit.mockClear();
		const view = render(
			<MantineProvider>
				<Form
					channelId="form-list-fields"
					initialValues={{ tags: ["react"] }}
					initialErrors={{ tags: "At least one tag is required" }}
					syncMode="change"
				>
					<Field
						name="tags"
						data={[
							{ value: "react", label: "React" },
							{ value: "vue", label: "Vue" },
						]}
						searchable={Field === MultiSelect ? true : undefined}
					/>
					<button type="submit">Submit</button>
				</Form>
			</MantineProvider>,
		);

		expect(view.getByText("At least one tag is required")).toBeTruthy();
		const input = view.getByRole("textbox");
		if (Field === MultiSelect) {
			fireEvent.click(input);
			fireEvent.click(view.getByRole("option", { name: "Vue" }));
		} else {
			fireEvent.change(input, { target: { value: "vue" } });
			fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
		}

		expect(channel.emit).toHaveBeenCalledWith("syncValues", {
			reason: "change",
			path: "tags",
			values: { tags: ["react", "vue"] },
		});
		fireEvent.submit(view.container.querySelector("form")!);
		expect(submittedValues()).toEqual({
			tags: ["react", "vue"],
		});
	});

	it("submits CheckboxGroup values as a list", () => {
		submitForm.mockClear();
		channel.emit.mockClear();
		const view = render(
			<MantineProvider>
				<Form
					channelId="form-checkbox-group"
					initialValues={{ privileges: ["admin"] }}
					syncMode="change"
				>
					<CheckboxGroup name="privileges" label="Privileges">
						<Checkbox value="admin" label="Admin" />
						<Checkbox value="editor" label="Editor" />
					</CheckboxGroup>
					<button type="submit">Submit</button>
				</Form>
			</MantineProvider>,
		);

		expect((view.getByRole("checkbox", { name: "Admin" }) as HTMLInputElement).checked).toBe(
			true,
		);
		fireEvent.click(view.getByRole("checkbox", { name: "Editor" }));
		expect(channel.emit).toHaveBeenCalledWith("syncValues", {
			reason: "change",
			path: "privileges",
			values: { privileges: ["admin", "editor"] },
		});
		fireEvent.submit(view.container.querySelector("form")!);
		expect(submittedValues()).toEqual({
			privileges: ["admin", "editor"],
		});
	});
});
