import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type ComponentPropsWithoutRef,
  type FormEvent,
  type ReactNode,
} from "react";
import { useForm } from "@mantine/form";
import type { UseFormInput, UseFormReturnType } from "@mantine/form";
import { FormProvider } from "./context";
import { submitForm, serialize } from "pulse-ui-client";
import {
  isValidatorSchema,
  schemaToRules,
  type ValidatorSchema,
} from "./validators";

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

export interface MantineFormProps<TValues = any>
  extends Omit<
    ComponentPropsWithoutRef<"form">,
    "onSubmit" | "onReset" | "action"
  > {
  children?: ReactNode;
  /** Initial values/errors/dirty/touched passed to useForm */
  initialValues?: UseFormInput<TValues>["initialValues"];
  initialErrors?: UseFormInput<TValues>["initialErrors"];
  initialDirty?: UseFormInput<TValues>["initialDirty"];
  initialTouched?: UseFormInput<TValues>["initialTouched"];
  /** Mantine useForm options */
  mode?: "controlled" | "uncontrolled";
  /** Serialized validation spec */
  validate?: ValidatorSchema;
  validateInputOnBlur?: boolean | string[];
  validateInputOnChange?: boolean | string[];
  clearInputErrorOnChange?: boolean;
  /** Default debounce for server validation when validateInputOnChange is enabled */
  debounceMs?: number;
  /** Callback invoked when form reset event fires */
  action: string;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  onServerValidation?: (
    value: any,
    values: TValues,
    path: string
  ) => Promise<void>;
  onReset?: (event: FormEvent<HTMLFormElement>) => void;
  /** Log of messages to apply imperatively on the Mantine form */
  messages?: FormMessage[];
}

export function Form<
  TValues extends Record<string, any> = Record<string, any>,
>({
  children,
  action,
  validate,
  initialValues,
  initialErrors,
  initialDirty,
  initialTouched,
  messages,
  mode = "controlled",
  validateInputOnBlur,
  validateInputOnChange,
  clearInputErrorOnChange,
  onServerValidation,
  debounceMs: serverValidationDebounceMs = 250,
  onSubmit: userOnSubmit,
  onReset: userOnReset,
  ...formProps
}: MantineFormProps<TValues>) {
  const formRef = useRef<UseFormReturnType<TValues> | null>(null);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map()
  );
  const computedValidate = useMemo(() => {
    if (validate && isValidatorSchema(validate)) {
      return schemaToRules<TValues>(validate, {
        onServerValidation,
        validateInputOnChange,
        serverValidationDebounceMs,
        formRef,
        timersRef,
      });
    }
    return validate;
  }, [
    validate,
    onServerValidation,
    validateInputOnChange,
    serverValidationDebounceMs,
  ]);
  const form = useForm<TValues>({
    mode,
    validate: computedValidate,
    initialValues: initialValues as any,
    initialErrors: initialErrors as any,
    initialDirty: initialDirty as any,
    initialTouched: initialTouched as any,
    validateInputOnBlur,
    validateInputOnChange,
    clearInputErrorOnChange,
    onSubmitPreventDefault: "always",
  });
  formRef.current = form;

  // Cleanup outstanding timers on unmount
  useEffect(() => {
    return () => {
      timersRef.current.forEach((t) => clearTimeout(t));
      timersRef.current.clear();
    };
  }, []);

  // Apply incoming messages in order once
  const appliedCount = useRef(0);

  useEffect(() => {
    const list = messages || [];
    for (let i = appliedCount.current; i < list.length; i++) {
      const msg = list[i];
      switch (msg.type) {
        case "setValues":
          form.setValues(msg.values);
          break;
        case "setFieldValue":
          form.setFieldValue(msg.path, msg.value);
          break;
        case "insertListItem":
          form.insertListItem(msg.path, msg.item, msg.index);
          break;
        case "removeListItem":
          form.removeListItem(msg.path, msg.index);
          break;
        case "reorderListItem":
          form.reorderListItem(msg.path, { from: msg.from, to: msg.to });
          break;
        case "setErrors":
          form.setErrors(msg.errors);
          break;
        case "setFieldError":
          form.setFieldError(msg.path, msg.error);
          break;
        case "clearErrors":
          if (msg.paths && msg.paths.length > 0) {
            msg.paths.forEach((p) => form.clearFieldError(p));
          } else {
            form.clearErrors();
          }
          break;
        case "setTouched":
          form.setTouched(msg.touched);
          break;
        case "validate":
          form.validate();
          break;
        case "reset":
          form.resetTouched();
          form.resetDirty();
          if (msg.initialValues) form.setValues(msg.initialValues);
          break;
        default:
          break;
      }
    }
    appliedCount.current = list.length;
  }, [messages]);

  const submitHandler = useMemo(
    () =>
      form.onSubmit((values: TValues, event) => {
        // Split values into serializable data and files
        const { dataWithoutFiles, filesByPath } = extractDataAndFiles(values);

        // Serialize complex data (dates, sets, maps, refs) using v3 serializer
        const serialized = serialize(dataWithoutFiles);
        const formData = new FormData();
        formData.set("__data__", JSON.stringify(serialized));

        // Append files under their path; multiple files -> multiple entries with same key
        for (const [path, files] of filesByPath.entries()) {
          for (const file of files) {
            formData.append(path, file);
          }
        }

        submitForm({
          event: event!,
          onSubmit: userOnSubmit,
          action,
          formData,
          // Mantine will have already called event.preventDefault(), we want to ignore that
          force: true,
        });
      }),
    [form, userOnSubmit]
  );

  const resetHandler = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      userOnReset?.(event);
      form.onReset(event);
    },
    [form, userOnReset]
  );

  // Provide context passthrough
  const ctx = useMemo(() => {
    const getInputProps: typeof form.getInputProps = (
      path: any,
      options?: any
    ) => {
      return form.getInputProps(path, options);
    };
    return { form, getInputProps };
  }, [form]);

  return (
    <FormProvider value={ctx}>
      <form {...formProps} onSubmit={submitHandler} onReset={resetHandler}>
        {children}
      </form>
    </FormProvider>
  );
}

function extractDataAndFiles(values: any) {
  const filesByPath = new Map<string, File[]>();

  function isFileLike(v: any): v is File {
    return typeof File !== "undefined" && v instanceof File;
  }

  function pushFile(path: string, file: File) {
    const existing = filesByPath.get(path);
    if (existing) existing.push(file);
    else filesByPath.set(path, [file]);
  }

  function visit(node: any, path: string): any {
    if (node == null) return node;

    // File or FileList
    if (isFileLike(node)) {
      pushFile(path, node);
      return undefined;
    }
    if (typeof FileList !== "undefined" && node instanceof FileList) {
      for (let i = 0; i < node.length; i++) pushFile(path, node.item(i)!);
      return undefined;
    }

    // Array
    if (Array.isArray(node)) {
      const result = new Array(node.length);
      for (let i = 0; i < node.length; i++) {
        const childPath = path ? `${path}.${i}` : String(i);
        result[i] = visit(node[i], childPath);
      }
      return result;
    }

    // Plain object
    if (typeof node === "object") {
      const out: Record<string, any> = {};
      const keys = Object.keys(node);
      for (let i = 0; i < keys.length; i++) {
        const key = keys[i];
        const childPath = path ? `${path}.${key}` : key;
        const value = visit((node as any)[key], childPath);
        if (value !== undefined) out[key] = value;
      }
      return out;
    }

    // Primitive or other serializable values (Date, Map, Set handled by serializer)
    return node;
  }

  const dataWithoutFiles = visit(values, "");
  return { dataWithoutFiles, filesByPath } as const;
}
