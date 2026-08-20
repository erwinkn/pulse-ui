import type { UseFormReturnType } from "@mantine/form";
import type { ComponentType, FunctionComponent } from "react";
import { useFormContext } from "./context";

type Simplify<T> = { [K in keyof T]: T[K] } & {};

type GetInputPropsReturnType = Simplify<ReturnType<UseFormReturnType<any>["getInputProps"]>>;

interface ConnectedFieldOptions {
	inputType?: "input" | "checkbox";
	coerceEmptyString?: boolean;
	debounceOnChange?: boolean;
}

function coerceControlledTextValue(props: Record<string, any>, enabled: boolean) {
	if (!enabled) {
		return props;
	}
	if (Object.hasOwn(props, "value")) {
		props.value ??= "";
	}
}

type InputProps = Partial<GetInputPropsReturnType> & { name?: string };

export function useField<P extends InputProps>(
	props: P,
	options?: ConnectedFieldOptions,
): { inputProps: P; key: string | undefined } {
	const ctx = useFormContext();
	if (!props.name || !ctx) {
		return { inputProps: props, key: undefined };
	}
	const { form, serverOnChange, serverOnBlur } = ctx;
	const mantineProps = form.getInputProps(props.name, {
		type: options?.inputType,
	});
	const merged = { ...props, ...mantineProps } as P;
	const name = props.name;
	const onChange = (...args: any) => {
		merged.onChange?.(...args);
		serverOnChange(name, !!options?.debounceOnChange);
	};
	const onBlur = (...args: any) => {
		merged.onBlur?.(...args);
		serverOnBlur(name);
	};
	coerceControlledTextValue(merged, !!options?.coerceEmptyString);

	return {
		inputProps: { ...merged, onChange, onBlur } as P,
		key: form.key(name),
	};
}

export function createConnectedField<P extends InputProps>(
	Component: ComponentType<P>,
	options?: ConnectedFieldOptions,
) {
	const Connected: FunctionComponent<P & { name?: string }> = (props) => {
		const { inputProps, key } = useField(props, options);
		return <Component key={key} {...inputProps} />;
	};

	Connected.displayName = Component.displayName || Component.name || "Component";

	return Connected;
}
