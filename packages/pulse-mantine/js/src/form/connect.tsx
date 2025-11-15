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

export function useFieldProps<P extends InputProps>(props: P, options?: ConnectedFieldOptions): P {
	const ctx = useFormContext();
	if (!props.name || !ctx) {
		return props;
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

	return { ...merged, onChange, onBlur } as P;
}

export function createConnectedField<P extends InputProps>(
	Component: ComponentType<P>,
	options?: ConnectedFieldOptions,
): FunctionComponent<P> {
	const Connected = (props: P) => {
		const fieldProps = useFieldProps(props, options);
		return <Component {...fieldProps} />;
	};

	Connected.displayName = Component.displayName || Component.name || "Component";

	return Connected;
}
