import React, {
  useEffect,
  useMemo,
  useRef,
  type ComponentPropsWithoutRef,
} from "react";
import {
  useForm,
  isNotEmpty,
  isEmail,
  matches as matchesValidator,
  isInRange,
  hasLength as hasLengthValidator,
  matchesField,
  isJSONString,
  isNotEmptyHTML,
} from "@mantine/form";
import type {
  FormValidateInput,
  UseFormInput,
  UseFormReturnType,
} from "@mantine/form";
import { FormProvider } from "./context";

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
  extends ComponentPropsWithoutRef<"form"> {
  children?: React.ReactNode;
  /** Mantine useForm validate option */
  validate?: ValidatorSchema;
  /** Initial values/errors/dirty/touched passed to useForm */
  initialValues?: UseFormInput<TValues>["initialValues"];
  initialErrors?: UseFormInput<TValues>["initialErrors"];
  initialDirty?: UseFormInput<TValues>["initialDirty"];
  initialTouched?: UseFormInput<TValues>["initialTouched"];
  /** Log of messages to apply imperatively on the Mantine form */
  messages?: FormMessage[];
  /** Mantine useForm options */
  mode?: "controlled" | "uncontrolled";
  validateInputOnBlur?: boolean | string[];
  validateInputOnChange?: boolean | string[];
  clearInputErrorOnChange?: boolean;
  /** Form element behavior */
  onSubmitPreventDefault?: boolean;
  /** Server validation callback */
  onServerValidation?: (
    value: any,
    values: TValues,
    path: string
  ) => Promise<void>;
  /** Default debounce for server validation when validateInputOnChange is enabled */
  debounceMs?: number;
}

// Schema support: accept a normalized validator schema coming from Python,
// where each leaf is a validator spec or list of specs. We convert it to Mantine
// rules object of functions at runtime.
export type ValidatorSpec =
  | { $kind: "isNotEmpty"; error?: any }
  | { $kind: "isEmail"; error?: any }
  | { $kind: "matches"; pattern: string; flags?: string | null; error?: any }
  | { $kind: "isInRange"; min?: number; max?: number; error?: any }
  | {
      $kind: "hasLength";
      min?: number;
      max?: number;
      exact?: number;
      error?: any;
    }
  | { $kind: "matchesField"; field: string; error?: any }
  | { $kind: "isJSONString"; error?: any }
  | { $kind: "isNotEmptyHTML"; error?: any }
  | { $kind: "server"; debounceMs?: number };

export type ValidatorSchema = {
  [key: string]: ValidatorSchema | ValidatorSpec[] | ValidatorSpec;
};

function isValidatorSpecArray(x: any): x is ValidatorSpec[] {
  return (
    Array.isArray(x) &&
    x.every((i) => i && typeof i === "object" && "$kind" in i)
  );
}
function isValidatorSpec(x: any): x is ValidatorSpec {
  return x && typeof x === "object" && !Array.isArray(x) && "$kind" in x;
}

function isValidatorSchema(x: any): x is ValidatorSchema {
  if (!x || typeof x !== "object" || Array.isArray(x)) return false;
  return Object.values(x).some(
    (v) =>
      isValidatorSpec(v) ||
      isValidatorSpecArray(v) ||
      (v && typeof v === "object")
  );
}

// Compose multiple built-in validators into a single rule function
function composeSpecs(
  specs: ValidatorSpec[],
  options: {
    onServerValidation?: MantineFormProps["onServerValidation"];
    validateInputOnChange?: MantineFormProps["validateInputOnChange"];
    serverValidationDebounceMs: number;
    formRef: React.RefObject<UseFormReturnType<any> | null>;
    timersRef: React.RefObject<Map<string, ReturnType<typeof setTimeout>>>;
  }
) {
  const validators = specs.map((spec) => {
    switch (spec.$kind) {
      case "isNotEmpty":
        return isNotEmpty(spec.error);
      case "isEmail":
        return isEmail(spec.error);
      case "matches": {
        const re = new RegExp(spec.pattern, spec.flags ?? undefined);
        return matchesValidator(re, spec.error as any);
      }
      case "isInRange": {
        const opts: any = {};
        if (typeof spec.min === "number") opts.min = spec.min;
        if (typeof spec.max === "number") opts.max = spec.max;
        return isInRange(opts, spec.error as any);
      }
      case "hasLength": {
        if (typeof spec.exact === "number") {
          return (hasLengthValidator as any)(spec.exact, spec.error as any);
        }
        const opts: any = {};
        if (typeof spec.min === "number") opts.min = spec.min;
        if (typeof spec.max === "number") opts.max = spec.max;
        return hasLengthValidator(opts, spec.error as any);
      }
      case "matchesField":
        return (matchesField as any)((spec as any).field, spec.error as any);
      case "isJSONString":
        return isJSONString(spec.error as any);
      case "isNotEmptyHTML":
        return isNotEmptyHTML(spec.error as any);
      case "server": {
        const timers = options.timersRef?.current;
        const shouldDebounce = (path: string) => {
          const v = options.validateInputOnChange;
          if (v === true) return true;
          if (Array.isArray(v)) return v.includes(path as any);
          return false;
        };
        const call = async (value: any, values: any, path: string) => {
          if (!options.onServerValidation) return;
          // Server handler should set/clear errors imperatively via Pulse APIs; return value is ignored
          await options.onServerValidation(value, values, path);
        };
        return (value: any, values: any, path: string) => {
          if (shouldDebounce(path)) {
            const delay =
              typeof spec.debounceMs === "number"
                ? spec.debounceMs
                : options.serverValidationDebounceMs;
              console.log(`Waiting ${delay}ms`)
            if (timers) {
              const t = timers.get(path);
              if (t) clearTimeout(t);
              timers.set(
                path,
                setTimeout(() => {
                  void call(value, values, path);
                }, delay)
              );
            } else {
              // Fallback if ref missing
              setTimeout(() => {
                void call(value, values, path);
              }, delay);
            }
          } else {
            void call(value, values, path);
          }
          return null;
        };
      }
      default:
        return () => null;
    }
  });

  return (value: any, values: any, path: string) => {
    for (const v of validators) {
      const res = (v as any)(value, values, path);
      if (res) return res;
    }
    return null;
  };
}

function schemaToRules<TValues>(
  schema: ValidatorSchema,
  options: Parameters<typeof composeSpecs>[1]
): FormValidateInput<TValues> {
  const build = (node: ValidatorSchema | ValidatorSpec[]): any => {
    if (Array.isArray(node)) {
      return composeSpecs(node, options);
    }
    if (isValidatorSpec(node)) {
      return composeSpecs([node], options);
    }
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(node)) {
      out[k] = build(v as any);
    }
    return out;
  };
  return build(schema);
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
  mode = "controlled",
  validateInputOnBlur,
  validateInputOnChange,
  clearInputErrorOnChange,
  onSubmitPreventDefault,
  onServerValidation,
  debounceMs: serverValidationDebounceMs = 250,
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
  const form: UseFormReturnType<TValues> = useForm<TValues>({
    mode,
    validate: computedValidate,
    initialValues: initialValues as any,
    initialErrors: initialErrors as any,
    initialDirty: initialDirty as any,
    initialTouched: initialTouched as any,
    validateInputOnBlur,
    validateInputOnChange,
    clearInputErrorOnChange,
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

  const onSubmit: React.FormEventHandler<HTMLFormElement> = (e) => {
    form.validate();
    if (onSubmitPreventDefault) e.preventDefault();
  };

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
      <form {...formProps} onSubmit={onSubmit}>
        {children}
      </form>
    </FormProvider>
  );
}
