import React, { createContext, useContext } from "react";
import type { UseFormReturnType } from "@mantine/form";

export type FormValidationMode = "submit" | "blur" | "change";

export interface FormContextValue<TValues = any> {
  form: UseFormReturnType<TValues>;
  /** Shortcut for list operations */
  insertListItem: UseFormReturnType<TValues>["insertListItem"];
  removeListItem: UseFormReturnType<TValues>["removeListItem"];
  reorderListItem: UseFormReturnType<TValues>["reorderListItem"];
  /** Returns props to bind a field in uncontrolled mode */
  getInputProps: UseFormReturnType<TValues>["getInputProps"];
}

const FormContext = createContext<FormContextValue | null>(null);

export function useFormContext<TValues = any>() {
  const ctx = useContext(FormContext as React.Context<FormContextValue<TValues> | null>);
  return ctx;
}

export function FormProvider<TValues = any>({
  value,
  children,
}: {
  value: FormContextValue<TValues>;
  children: React.ReactNode;
}) {
  return <FormContext.Provider value={value as FormContextValue}>{children}</FormContext.Provider>;
}

