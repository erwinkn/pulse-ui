import { createContext, useContext, useMemo, type PropsWithChildren } from "react";
import type { UseFormReturnType } from "@mantine/form";

export type FormEventHandler = () => {};

export interface FormContext {
  form: UseFormReturnType<any>;
  serverOnChange: (path: string, debounce: boolean) => void;
  serverOnBlur: (path: string) => void;
}
const FormContext = createContext<FormContext | null>(null);

export function useFormContext() {
  return useContext(FormContext);
}

export function FormProvider<TValues = any>({
  form,
  children,
  serverOnBlur,
  serverOnChange,
}: PropsWithChildren<FormContext>) {
  const ctx = useMemo(
    () => ({ form, serverOnChange, serverOnBlur }),
    [form, serverOnChange, serverOnBlur]
  );
  return <FormContext.Provider value={ctx}>{children}</FormContext.Provider>;
}
