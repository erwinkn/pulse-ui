import { describe, expect, it } from "bun:test";
import { useForm, type UseFormReturnType } from "@mantine/form";
import { type ComponentPropsWithoutRef, type ComponentType } from "react";
import { act, fireEvent, render } from "@testing-library/react";
import { createConnectedField, useField } from "./connect";
import { FormProvider } from "./context";

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
});
