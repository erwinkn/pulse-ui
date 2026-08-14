import { beforeEach, describe, expect, it, mock } from "bun:test";
import { MantineProvider } from "@mantine/core";
import { fireEvent, render } from "@testing-library/react";
import { useField } from "./connect";
import { Checkbox, CheckboxGroup, MultiSelect, TagsInput, TextInput } from "./fields";

const channels = new Map<
	string,
	{ closed: boolean; on: () => () => void; emit: ReturnType<typeof mock> }
>();

function channelFor(id: string) {
	let channel = channels.get(id);
	if (!channel) {
		channel = {
			closed: false,
			on: () => () => {},
			emit: mock(() => {}),
		};
		channels.set(id, channel);
	}
	return channel;
}

const usePulseChannel = mock((id: string) => channelFor(id));
let currentDirectives = {
	query: { pulse_deployment: "prod-old" },
};
const directivesSource = () => currentDirectives;
const submitForm = mock(
	(_options: { values: unknown; directives?: typeof directivesSource }) => {},
);

mock.module("pulse-ui-client", () => ({
	submitForm,
	usePulseChannel,
	usePulseDirectivesSource: () => directivesSource,
}));

const { Form } = await import("./form");

beforeEach(() => {
	channels.clear();
});

type Sample = {
	sample_id: string;
	project: {
		name: string;
		metadata: { kind: string };
	};
};

type ListInputProps = {
	name: string;
	onChange?: (value: Sample[]) => void;
};

function CommitRows({ rows }: { rows: Sample[] }) {
	const { inputProps, key } = useField<ListInputProps>(
		{ name: "samples" },
		{ debounceOnChange: true },
	);

	return (
		<button
			key={key}
			type="button"
			onClick={() => inputProps.onChange?.([...rows])}
		>
			Commit rows
		</button>
	);
}

const listCommitCases: Array<[string, Sample[]]> = [
	["empty", []],
	[
		"one",
		[
			{
				sample_id: "sample-1",
				project: { name: "Project A", metadata: { kind: "single" } },
			},
		],
	],
	[
		"two",
		[
			{
				sample_id: "sample-1",
				project: { name: "Project A", metadata: { kind: "first" } },
			},
			{
				sample_id: "sample-2",
				project: { name: "Project B", metadata: { kind: "second" } },
			},
		],
	],
];

const listFields = [
	["MultiSelect", MultiSelect],
	["TagsInput", TagsInput],
] as const;

function submittedValues() {
	return submitForm.mock.calls.at(-1)?.[0]?.values as Record<string, unknown>;
}

describe("MantineForm list-valued fields", () => {
	it.each(listCommitCases)(
		"reproduces custom useField list commit for %s rows",
		(_label, rows) => {
			submitForm.mockClear();
			const view = render(
				<MantineProvider>
					<Form
						channelId="form-custom-list-repro"
						mode="uncontrolled"
						initialValues={{ samples: rows }}
						syncMode="change"
						debounceMs={0}
					>
						<CommitRows rows={rows} />
						<button type="submit">Submit</button>
					</Form>
				</MantineProvider>,
			);

			fireEvent.click(view.getByRole("button", { name: "Commit rows" }));
			const sync = channelFor("form-custom-list-repro").emit.mock.calls.find(
				([event]) => event === "syncValues",
			)?.[1];
			expect(sync?.values).toEqual({ samples: rows });

			fireEvent.submit(view.container.querySelector("form")!);
			expect(submittedValues()).toEqual({ samples: rows });
			expect(Array.isArray(submittedValues().samples)).toBe(true);
		},
	);

	it.each(listFields)("submits %s values as a list", (_label, Field) => {
		submitForm.mockClear();
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

		expect(channelFor("form-list-fields").emit).toHaveBeenCalledWith("syncValues", {
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
		expect(channelFor("form-checkbox-group").emit).toHaveBeenCalledWith("syncValues", {
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

describe("MantineForm submit values", () => {
	it("passes live Pulse directives to submitForm", () => {
		submitForm.mockClear();
		const view = render(
			<MantineProvider>
				<Form channelId="form-directives" action="/submit" initialValues={{ name: "Ada" }}>
					<TextInput name="name" label="Name" />
					<button type="submit">Submit</button>
				</Form>
			</MantineProvider>,
		);

		currentDirectives = {
			query: { pulse_deployment: "prod-current" },
		};
		fireEvent.submit(view.container.querySelector("form")!);

		const options = submitForm.mock.calls.at(-1)?.[0];
		expect(options?.directives).toBe(directivesSource);
		expect(options?.directives?.()).toEqual(currentDirectives);
	});

	it("submits shadowable field names as values", () => {
		submitForm.mockClear();
		const view = render(
			<MantineProvider>
				<Form
					channelId="form-name-field"
					initialValues={{ name: "qgis", action: "save", method: "post", id: "record-1" }}
					id="profile-form"
					method="post"
					target="_blank"
					action="/submit"
				>
					<TextInput name="name" label="Name" />
					<TextInput name="action" label="Action" />
					<TextInput name="method" label="Method" />
					<TextInput name="id" label="Record ID" />
					<button type="submit">Submit</button>
				</Form>
			</MantineProvider>,
		);

		fireEvent.submit(view.container.querySelector("form")!);

		expect(submittedValues()).toEqual({
			name: "qgis",
			action: "save",
			method: "post",
			id: "record-1",
		});
	});
});

describe("MantineForm channel timer lifecycle", () => {
	it("drops debounced sync and validation when the bridge is replaced", async () => {
		const view = render(
			<MantineProvider>
				<Form
					channelId="form-old"
					initialValues={{ name: "" }}
					syncMode="change"
					debounceMs={10}
					validateInputOnChange
					validate={{
						name: { $kind: "server", debounceMs: 10, runOn: "change" },
					}}
				>
					<TextInput name="name" label="Name" />
				</Form>
			</MantineProvider>,
		);
		fireEvent.change(view.getByRole("textbox"), { target: { value: "Ada" } });

		view.rerender(
			<MantineProvider>
				<Form channelId="form-new" initialValues={{ name: "Ada" }}>
					<TextInput name="name" label="Name" />
				</Form>
			</MantineProvider>,
		);
		await new Promise((resolve) => setTimeout(resolve, 20));

		expect(channelFor("form-old").emit).not.toHaveBeenCalled();
	});

	it("fires server validation after the debounce", async () => {
		const view = render(
			<MantineProvider>
				<Form
					channelId="form-reset"
					initialValues={{ name: "" }}
					debounceMs={1}
					validateInputOnChange
					validate={{
						name: { $kind: "server", debounceMs: 1, runOn: "change" },
					}}
				>
					<TextInput name="name" label="Name" />
				</Form>
			</MantineProvider>,
		);

		fireEvent.change(view.getByRole("textbox"), { target: { value: "Grace" } });
		await new Promise((resolve) => setTimeout(resolve, 10));

		expect(channelFor("form-reset").emit).toHaveBeenCalledWith("serverValidate", {
			path: "name",
			value: "Grace",
			values: { name: "Grace" },
		});
		view.unmount();
	});

	it("fires value sync after the debounce", async () => {
		const view = render(
			<MantineProvider>
				<Form
					channelId="form-sync-reset"
					initialValues={{ name: "" }}
					syncMode="change"
					debounceMs={1}
				>
					<TextInput name="name" label="Name" />
				</Form>
			</MantineProvider>,
		);

		fireEvent.change(view.getByRole("textbox"), { target: { value: "Lin" } });
		await new Promise((resolve) => setTimeout(resolve, 10));

		expect(channelFor("form-sync-reset").emit).toHaveBeenCalledWith("syncValues", {
			path: "name",
			reason: "change",
			values: { name: "Lin" },
		});
		view.unmount();
	});
});
