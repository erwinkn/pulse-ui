import type { UseFormReturnType } from "@mantine/form";
import type {
	ChangeEvent,
	ComponentProps,
	ComponentType,
	FormEvent,
	FunctionComponent,
	PropsWithChildren,
	ReactNode,
} from "react";
import { useFormContext } from "./context";

export type SyncBehavior = "debounced" | "instant";

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

export function createConnectedField<P extends InputProps>(
	Component: ComponentType<P>,
	options?: ConnectedFieldOptions,
): FunctionComponent<P> {
	const Connected = (props: P) => {
		const ctx = useFormContext();
		if (!props.name || !ctx) {
			return <Component {...props} />;
		}
		const { form, serverOnChange, serverOnBlur } = ctx;
		const mantineProps = form.getInputProps(props.name, {
			type: options?.inputType,
		});
		const merged = { ...props, ...mantineProps };
		const name = props.name;
		const onChange = (...args: any) => {
			merged.onChange(...args);
			serverOnChange(name, !!options?.debounceOnChange);
		};
		const onBlur = (...args: any) => {
			merged.onBlur(...args);
			serverOnBlur(name);
		};
		coerceControlledTextValue(merged, !!options?.coerceEmptyString);

		return <Component {...merged} onChange={onChange} onBlur={onBlur} />;
	};

	Connected.displayName = Component.displayName || Component.name || "Component";

	return Connected;
}
