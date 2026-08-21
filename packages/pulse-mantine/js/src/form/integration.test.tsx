import { describe, expect, it, mock } from "bun:test";
import { Combobox as MantineCombobox, MantineProvider } from "@mantine/core";
import { act, fireEvent, render } from "@testing-library/react";
import { useField } from "./connect";
import { Checkbox, CheckboxGroup, MultiSelect, TagsInput, TextInput } from "./fields";

const channelHandlers = new Map<string, (payload?: any) => any>();
const channel = {
	on: mock((event: string, handler: (payload?: any) => any) => {
		channelHandlers.set(event, handler);
		return () => {
			if (channelHandlers.get(event) === handler) {
				channelHandlers.delete(event);
			}
		};
	}),
	emit: mock(),
};
const client = {
	channel: () => channel,
	attachHandle: () => {},
	detachHandle: () => {},
};
let currentDirectives = {
	query: { pulse_deployment: "prod-old" },
};
const directivesSource = () => currentDirectives;
const submitForm = mock(
	(_options: { values: unknown; directives?: typeof directivesSource }) => {},
);

mock.module("pulse-ui-client", () => ({
	submitForm,
	usePulseClient: () => client,
	useChannel: () => channel,
	usePulseDirectivesSource: () => directivesSource,
}));

const { Form } = await import("./form");
const { Combobox } = await import("../combobox");
const { Tree } = await import("../tree");

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
			channel.emit.mockClear();
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
			const sync = channel.emit.mock.calls.find(
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

describe("Mantine channel handlers", () => {
	it("registers Combobox handlers once across re-renders", () => {
		channel.on.mockClear();
		channelHandlers.clear();
		const view = render(
			<MantineProvider>
				<Combobox channelId="combobox" />
			</MantineProvider>,
		);
		const registrations = channel.on.mock.calls.length;
		view.rerender(
			<MantineProvider>
				<Combobox channelId="combobox" />
			</MantineProvider>,
		);
		expect(registrations).toBeGreaterThan(0);
		expect(channel.on).toHaveBeenCalledTimes(registrations);
		view.unmount();
	});

	it("registers Tree handlers once across re-renders", () => {
		channel.on.mockClear();
		channelHandlers.clear();
		const view = render(
			<MantineProvider>
				<Tree channelId="tree" data={[]} />
			</MantineProvider>,
		);
		const registrations = channel.on.mock.calls.length;
		view.rerender(
			<MantineProvider>
				<Tree channelId="tree" data={[]} />
			</MantineProvider>,
		);
		expect(registrations).toBeGreaterThan(0);
		expect(channel.on).toHaveBeenCalledTimes(registrations);
		view.unmount();
	});

	it("uses Mantine's stable selected-option getter", () => {
		channel.on.mockClear();
		channelHandlers.clear();
		const view = render(
			<MantineProvider>
				<Combobox channelId="combobox">
					<MantineCombobox.Options id="list">
						<MantineCombobox.Option value="one">One</MantineCombobox.Option>
					</MantineCombobox.Options>
				</Combobox>
			</MantineProvider>,
		);
		act(() => {
			channelHandlers.get("setListId")?.({ listId: "list" });
			channelHandlers.get("selectOption")?.({ index: 0 });
		});
		expect(channelHandlers.get("getSelectedOptionIndex")?.()).toBe(0);
		view.unmount();
	});

	it("returns a channel-assigned list id", () => {
		channel.on.mockClear();
		channelHandlers.clear();
		const view = render(
			<MantineProvider>
				<Combobox channelId="combobox" />
			</MantineProvider>,
		);
		act(() => {
			channelHandlers.get("setListId")?.({ listId: "channel-list" });
		});
		expect(channelHandlers.get("getListId")?.()).toBe("channel-list");
		view.unmount();
	});
});
