import type { UseFormReturnType } from "@mantine/form";
import { createContext, type PropsWithChildren, useContext, useMemo } from "react";

export interface FormContext {
	form: UseFormReturnType<any>;
	serverOnChange: (path: string, debounce: boolean) => void;
	serverOnBlur: (path: string) => void;
}
const FormContext = createContext<FormContext | null>(null);

export function useFormContext() {
	return useContext(FormContext);
}

export function FormProvider({
	form,
	children,
	serverOnBlur,
	serverOnChange,
}: PropsWithChildren<FormContext>) {
	const ctx = useMemo(
		() => ({ form, serverOnChange, serverOnBlur }),
		[form, serverOnChange, serverOnBlur],
	);
	return <FormContext.Provider value={ctx}>{children}</FormContext.Provider>;
}
