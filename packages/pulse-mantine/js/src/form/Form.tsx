import React, { useEffect, useMemo, useRef } from "react";
import { useForm } from "@mantine/form";
import type { UseFormInput, UseFormReturnType } from "@mantine/form";
import { FormProvider, type FormValidationMode } from "./context";

export type FormMessage =
  | { type: "setValues"; values: any }
  | { type: "setFieldValue"; path: string; value: any }
  | { type: "insertListItem"; path: string; item: any; index?: number }
  | { type: "removeListItem"; path: string; index: number }
  | { type: "reorderListItem"; path: string; from: number; to: number }
  | { type: "setErrors"; errors: Record<string, any> }
  | { type: "setFieldError"; path: string; error: any }
  | { type: "clearErrors"; paths?: string[] }
  | { type: "setTouched"; touched: Record<string, boolean> }
  | { type: "validate" }
  | { type: "reset"; initialValues?: any };

export interface MantineFormProps<TValues = any> {
  children?: React.ReactNode;
  /** Mantine useForm validate option */
  validate?: UseFormInput<TValues>["validate"];
  /** Initial values/errors/dirty/touched passed to useForm */
  initialValues?: UseFormInput<TValues>["initialValues"];
  initialErrors?: UseFormInput<TValues>["initialErrors"];
  initialDirty?: UseFormInput<TValues>["initialDirty"];
  initialTouched?: UseFormInput<TValues>["initialTouched"];
  /** Log of messages to apply imperatively on the Mantine form */
  messages?: FormMessage[];
  /** Validation behavior */
  validationMode?: FormValidationMode;
  validationDebounce?: number;
  /** Additional props for underlying form element */
  formProps?: React.ComponentPropsWithoutRef<"form">;
}

function deepEqual(a: any, b: any) {
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return a === b;
  }
}
function useDebounced<T extends (...args: any[]) => void>(
  fn: T,
  delay: number
) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  return (...args: Parameters<T>) => {
    if (timeout.current) clearTimeout(timeout.current);
    timeout.current = setTimeout(() => fnRef.current(...args), delay);
  };
}

export function Form<
  TValues extends Record<string, any> = Record<string, any>,
>({
  children,
  validate,
  initialValues,
  initialErrors,
  initialDirty,
  initialTouched,
  messages,
  validationMode = "submit",
  validationDebounce = 250,
  formProps,
}: MantineFormProps<TValues>) {
  const form: UseFormReturnType<TValues> = useForm<TValues>({
    mode: "uncontrolled",
    validate,
    initialValues: initialValues as any,
    initialErrors: initialErrors as any,
    initialDirty: initialDirty as any,
    initialTouched: initialTouched as any,
    validateInputOnBlur: validationMode === "blur",
    validateInputOnChange: validationMode === "change",
  });

  // Apply incoming messages in order once
  const appliedCount = useRef(0);
  useEffect(() => {
    const list = messages || [];
    for (let i = appliedCount.current; i < list.length; i++) {
      const msg = list[i];
      switch (msg.type) {
        case "setValues":
          form.setValues(msg.values as any);
          break;
        case "setFieldValue":
          form.setFieldValue(msg.path as any, msg.value);
          break;
        case "insertListItem":
          form.insertListItem(msg.path as any, msg.item, (msg as any).index);
          break;
        case "removeListItem":
          form.removeListItem(msg.path as any, msg.index);
          break;
        case "reorderListItem":
          form.reorderListItem(msg.path as any, { from: msg.from, to: msg.to });
          break;
        case "setErrors":
          form.setErrors(msg.errors as any);
          break;
        case "setFieldError":
          form.setFieldError(msg.path as any, msg.error);
          break;
        case "clearErrors":
          if (msg.paths && msg.paths.length > 0) {
            msg.paths.forEach((p) => form.clearFieldError(p as any));
          } else {
            form.clearErrors();
          }
          break;
        case "setTouched":
          form.setTouched(msg.touched as any);
          break;
        case "validate":
          form.validate();
          break;
        case "reset":
          form.resetTouched();
          form.resetDirty();
          if (msg.initialValues) form.setValues(msg.initialValues as any);
          break;
        default:
          break;
      }
    }
    appliedCount.current = list.length;
  }, [messages]);

  // Debounced validation on change when requested
  const debouncedValidate = useDebounced(
    () => form.validate(),
    validationDebounce
  );

  const onSubmit: React.FormEventHandler<HTMLFormElement> = (e) => {
    if (validationMode === "submit") {
      const res = form.validate();
      if (res.hasErrors) {
        e.preventDefault();
      }
    }
    // For change/blur modes, validation already happened; let Pulse handle submit
  };

  // Provide context and optionally attach debounced validation hooks via proxy getInputProps
  const ctx = useMemo(() => {
    const getInputProps: typeof form.getInputProps = (
      path: any,
      options?: any
    ) => {
      const props = form.getInputProps(path, options);
      if (validationMode === "change" && props.onChange) {
        const orig = props.onChange;
        props.onChange = (...args: any[]) => {
          // @ts-ignore
          orig(...args);
          debouncedValidate();
        };
      }
      return props;
    };
    return {
      form,
      insertListItem: form.insertListItem,
      removeListItem: form.removeListItem,
      reorderListItem: form.reorderListItem,
      getInputProps,
    };
  }, [form, validationMode, validationDebounce]);

  return (
    <FormProvider value={ctx}>
      <form {...formProps} onSubmit={onSubmit}>
        {children}
      </form>
    </FormProvider>
  );
}
