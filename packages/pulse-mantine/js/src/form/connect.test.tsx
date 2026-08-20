import { describe, expect, it } from "bun:test";
import { MantineProvider } from "@mantine/core";
import { useForm, type UseFormReturnType } from "@mantine/form";
import {
	type ComponentPropsWithoutRef,
	type ComponentType,
	type ReactNode,
} from "react";
import { act, fireEvent, render } from "@testing-library/react";
import { createConnectedField, useField } from "./connect";
import { FormProvider } from "./context";
import { MultiSelect, TagsInput } from "./fields";

type InputProps = ComponentPropsWithoutRef<"input">;

function Input(props: InputProps) {
	return <input {...props} />;
}

const ConnectedInput = createConnectedField(Input);

function HookInput(props: InputProps) {
	const { inputProps, key } = useField(props);
	return <input key={key} {...inputProps} />;
}

function renderForm(
	mode: "controlled" | "uncontrolled",
	Field: ComponentType<InputProps> = ConnectedInput,
) {
	let form!: UseFormReturnType<{ page: string }>;

	function Harness() {
		form = useForm({ mode, initialValues: { page: "1" } });
		return (
			<FormProvider form={form} serverOnChange={() => {}} serverOnBlur={() => {}}>
				<Field name="page" />
			</FormProvider>
		);
	}

	const view = render(<Harness />);

	return {
		form: () => form,
		input: () => view.getByRole("textbox") as HTMLInputElement,
		unmount: view.unmount,
	};
}

type FormMode = "controlled" | "uncontrolled";
type ListValues = { tags: string[] };

function renderListField(
	mode: FormMode,
	field: (name: string) => ReactNode,
	initialValues: ListValues,
	pillSelector: string,
) {
	let form!: UseFormReturnType<ListValues>;
	let submitted: ListValues | undefined;
	let synced: ListValues | undefined;

	function Harness() {
		form = useForm({ mode, initialValues });
		return (
			<MantineProvider>
				<FormProvider
					form={form}
					serverOnChange={() => {
						synced = form.getValues();
					}}
					serverOnBlur={() => {}}
				>
					<form
						onSubmit={form.onSubmit((values) => {
							submitted = values;
						})}
					>
						{field("tags")}
						<button type="submit">Submit</button>
					</form>
				</FormProvider>
			</MantineProvider>
		);
	}

	const view = render(<Harness />);
	return {
		view,
		form: () => form,
		submitted: () => submitted,
		synced: () => synced,
		pills: () =>
			Array.from(view.container.querySelectorAll(pillSelector)).map(
				(pill) => pill.textContent,
			),
	};
}

describe("form field connections", () => {
	it("remounts an uncontrolled input after a programmatic field update", () => {
		const view = renderForm("uncontrolled");
		const initialInput = view.input();
		expect(initialInput.value).toBe("1");

		fireEvent.change(initialInput, { target: { value: "typed" } });
		expect(view.form().getValues().page).toBe("typed");
		expect(view.input()).toBe(initialInput);

		act(() => view.form().setFieldValue("page", "2"));
		expect(view.input().value).toBe("2");
		expect(view.input()).not.toBe(initialInput);

		view.unmount();
	});

	it("does not remount a controlled input after a programmatic field update", () => {
		const view = renderForm("controlled");
		const initialInput = view.input();
		expect(initialInput.value).toBe("1");

		act(() => view.form().setFieldValue("page", "2"));
		expect(view.input().value).toBe("2");
		expect(view.input()).toBe(initialInput);

		view.unmount();
	});

	it("returns the key separately for custom uncontrolled inputs", () => {
		const view = renderForm("uncontrolled", HookInput);
		const initialInput = view.input();

		act(() => view.form().setFieldValue("page", "2"));
		expect(view.input().value).toBe("2");
		expect(view.input()).not.toBe(initialInput);

		view.unmount();
	});

	it.each(["controlled", "uncontrolled"] as const)(
		"round-trips MultiSelect values in %s mode",
		(mode) => {
			const listField = renderListField(
				mode,
				(name) => (
					<MultiSelect
						name={name}
						data={[
							{ value: "react", label: "React" },
							{ value: "vue", label: "Vue" },
						]}
						searchable
					/>
				),
				{ tags: ["react"] },
				".mantine-MultiSelect-pill",
			);
			const input = listField.view.getByRole("textbox");
			expect(listField.pills()).toContain("React");

			fireEvent.click(input);
			fireEvent.click(listField.view.getByRole("option", { name: "Vue" }));
			expect(listField.form().getValues()).toEqual({ tags: ["react", "vue"] });
			expect(listField.synced()).toEqual({ tags: ["react", "vue"] });

			fireEvent.submit(listField.view.container.querySelector("form")!);
			expect(listField.submitted()).toEqual({ tags: ["react", "vue"] });

			act(() => listField.form().setValues({ tags: ["vue"] }));
			expect(listField.pills()).toContain("Vue");
			expect(listField.pills()).not.toContain("React");

			act(() => listField.form().reset());
			expect(listField.pills()).toContain("React");
		},
	);

	it.each(["controlled", "uncontrolled"] as const)(
		"round-trips TagsInput values in %s mode",
		(mode) => {
			const listField = renderListField(
				mode,
				(name) => <TagsInput name={name} data={["alpha", "beta", "gamma"]} />,
				{ tags: ["alpha", "beta"] },
				".mantine-TagsInput-pill",
			);
			const input = listField.view.getByRole("textbox");
			expect(listField.pills()).toContain("alpha");
			expect(listField.pills()).toContain("beta");

			fireEvent.change(input, { target: { value: "gamma" } });
			fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
			expect(listField.form().getValues()).toEqual({
				tags: ["alpha", "beta", "gamma"],
			});
			expect(listField.synced()).toEqual({
				tags: ["alpha", "beta", "gamma"],
			});

			fireEvent.submit(listField.view.container.querySelector("form")!);
			expect(listField.submitted()).toEqual({
				tags: ["alpha", "beta", "gamma"],
			});

			act(() => listField.form().setValues({ tags: ["gamma"] }));
			expect(listField.pills()).toContain("gamma");
			expect(listField.pills()).not.toContain("alpha");

			act(() => listField.form().reset());
			expect(listField.pills()).toContain("alpha");
			expect(listField.pills()).toContain("beta");
		},
	);
});
