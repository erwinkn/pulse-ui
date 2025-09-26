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
import { submitForm, serialize, usePulseChannel } from "pulse-ui-client";
import {
  isValidatorSchema,
  schemaToRules,
  type ValidatorSchema,
} from "./validators";

export interface MantineFormProps<TValues = any>
  extends Omit<
    ComponentPropsWithoutRef<"form">,
    "onSubmit" | "onReset" | "action"
  > {
  channelId: string;
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
  cascadeUpdates?: boolean;
  /** Default debounce for server validation when validateInputOnChange is enabled */
  debounceMs?: number;
  /** Callback invoked when form reset event fires */
  action: string;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onServerValidation?: (value: any, values: TValues, path: string) => void;
  onReset?: (event: FormEvent<HTMLFormElement>) => void;
}

export function Form<
  TValues extends Record<string, any> = Record<string, any>,
>({
  children,
  action,
  channelId,
  validate,
  initialValues,
  initialErrors,
  initialDirty,
  initialTouched,
  mode = "controlled",
  validateInputOnBlur,
  validateInputOnChange,
  clearInputErrorOnChange,
  onServerValidation,
  debounceMs: serverValidationDebounceMs = 250,
  onSubmit: userOnSubmit,
  onReset: userOnReset,
  cascadeUpdates,
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
    cascadeUpdates,
  });
  formRef.current = form;

  const channel = usePulseChannel(channelId);

  // Cleanup outstanding timers on unmount
  useEffect(() => {
    return () => {
      timersRef.current.forEach((t) => clearTimeout(t));
      timersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const cleanups = [
      channel.on("setValues", (payload: { values: TValues }) => {
        if (payload?.values !== undefined) {
          form.setValues(payload.values);
        }
      }),
      channel.on("setFieldValue", (payload: { path: string; value: any }) => {
        if (!payload) return;
        form.setFieldValue(payload.path, payload.value);
      }),
      channel.on(
        "insertListItem",
        (payload: { path: string; item: any; index?: number }) => {
          if (!payload) return;
          form.insertListItem(payload.path, payload.item, payload.index);
        }
      ),
      channel.on("removeListItem", (payload: { path: string; index: number }) => {
        if (!payload) return;
        form.removeListItem(payload.path, payload.index);
      }),
      channel.on(
        "reorderListItem",
        (payload: { path: string; from: number; to: number }) => {
          if (!payload) return;
          form.reorderListItem(payload.path, { from: payload.from, to: payload.to });
        }
      ),
      channel.on("setErrors", (payload: { errors: Record<string, any> }) => {
        if (!payload) return;
        form.setErrors(payload.errors);
      }),
      channel.on("setFieldError", (payload: { path: string; error: any }) => {
        if (!payload) return;
        form.setFieldError(payload.path, payload.error);
      }),
      channel.on("clearErrors", (payload?: { paths?: string[] }) => {
        const paths = payload?.paths;
        if (Array.isArray(paths) && paths.length > 0) {
          paths.forEach((p) => form.clearFieldError(p));
        } else {
          form.clearErrors();
        }
      }),
      channel.on(
        "setTouched",
        (payload: { touched: Record<string, boolean> }) => {
          if (!payload) return;
          form.setTouched(payload.touched);
        }
      ),
      channel.on("validate", () => {
        form.validate();
      }),
      channel.on("reset", (payload?: { initialValues?: TValues }) => {
        if (payload?.initialValues) {
          // Same behavior as form.reset(), except we allow modifying the initialValues
          form.resetTouched();
          form.resetDirty();
          form.setValues(payload.initialValues);
        } else {
          form.reset()
        }
      }),
      channel.on("getFormValues", () => form.getValues()),
    ];

    return () => {
      for (const dispose of cleanups) dispose();
    };
  }, [channel, form]);

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
