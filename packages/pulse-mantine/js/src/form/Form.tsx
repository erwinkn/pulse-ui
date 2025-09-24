import React, {
  useCallback,
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
import { submitForm } from "pulse-ui-client";

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
  children?: React.ReactNode;
  /** Initial values/errors/dirty/touched passed to useForm */
  initialValues?: UseFormInput<TValues>["initialValues"];
  initialErrors?: UseFormInput<TValues>["initialErrors"];
  initialDirty?: UseFormInput<TValues>["initialDirty"];
  initialTouched?: UseFormInput<TValues>["initialTouched"];
  /** Mantine useForm options */
  mode?: "controlled" | "uncontrolled";
  validateInputOnBlur?: boolean | string[];
  validateInputOnChange?: boolean | string[];
  clearInputErrorOnChange?: boolean;
  /** Default debounce for server validation when validateInputOnChange is enabled */
  debounceMs?: number;
  /** Callback invoked when form reset event fires */
  onReset?: (event: React.FormEvent<HTMLFormElement>) => void;
  /** -- Internal props -- */
  action: string;
  onSubmit?: (event: React.FormEvent<HTMLFormElement>) => void | Promise<void>;
  onServerValidation?: (
    value: any,
    values: TValues,
    path: string
  ) => Promise<void>;
  /** Serialized validation spec */
  validate?: ValidatorSchema;
  /** Log of messages to apply imperatively on the Mantine form */
  messages?: FormMessage[];
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
  | {
      $kind: "isUrl";
      protocols?: string[] | null;
      requireProtocol?: boolean;
      error?: any;
    }
  | { $kind: "isUUID"; version?: 1 | 2 | 3 | 4 | 5; error?: any }
  | { $kind: "isULID"; error?: any }
  | { $kind: "isNumber"; error?: any }
  | { $kind: "isInteger"; error?: any }
  | { $kind: "isDate"; error?: any }
  | { $kind: "isISODate"; withTime?: boolean; error?: any }
  | {
      $kind: "isBefore";
      field?: string;
      value?: any;
      inclusive?: boolean;
      error?: any;
    }
  | {
      $kind: "isAfter";
      field?: string;
      value?: any;
      inclusive?: boolean;
      error?: any;
    }
  | { $kind: "minItems"; count: number; error?: any }
  | { $kind: "maxItems"; count: number; error?: any }
  | { $kind: "isArrayNotEmpty"; error?: any }
  | {
      $kind: "allowedFileTypes";
      mimeTypes?: string[] | null;
      extensions?: string[] | null;
      error?: any;
    }
  | { $kind: "maxFileSize"; bytes: number; error?: any }
  | {
      $kind: "requiredWhen";
      field: string;
      equals?: any;
      notEquals?: any;
      in?: any[] | null;
      notIn?: any[] | null;
      truthy?: boolean;
      error?: any;
    }
  | {
      $kind: "requiredUnless";
      field: string;
      equals?: any;
      notEquals?: any;
      in?: any[] | null;
      notIn?: any[] | null;
      truthy?: boolean;
      error?: any;
    }
  | { $kind: "startsWith"; value: string; caseSensitive?: boolean; error?: any }
  | { $kind: "endsWith"; value: string; caseSensitive?: boolean; error?: any }
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

function isEmptyValue(value: any): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim().length === 0;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof FileList !== "undefined" && value instanceof FileList) {
    return value.length === 0;
  }
  return false;
}

function getValueAtPath(source: any, path?: string): any {
  if (!source || !path) return undefined;
  return path
    .split(".")
    .reduce(
      (acc: any, key: string) => (acc == null ? undefined : acc[key]),
      source
    );
}

function coerceNumber(value: any): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length === 0) return null;
    const num = Number(trimmed);
    return Number.isFinite(num) ? num : null;
  }
  if (value instanceof Number) {
    const num = Number(value.valueOf());
    return Number.isFinite(num) ? num : null;
  }
  return null;
}

function coerceComparable(value: any): number | null {
  if (value instanceof Date) {
    const ts = value.getTime();
    return Number.isNaN(ts) ? null : ts;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length === 0) return null;
    const numeric = Number(trimmed);
    if (Number.isFinite(numeric)) return numeric;
    const parsed = Date.parse(trimmed);
    return Number.isNaN(parsed) ? null : parsed;
  }
  if (value instanceof Number) {
    const num = Number(value.valueOf());
    return Number.isFinite(num) ? num : null;
  }
  return null;
}

function coerceDate(value: any): number | null {
  if (value instanceof Date) {
    const ts = value.getTime();
    return Number.isNaN(ts) ? null : ts;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length === 0) return null;
    const parsed = Date.parse(trimmed);
    return Number.isNaN(parsed) ? null : parsed;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (value instanceof Number) {
    const num = Number(value.valueOf());
    return Number.isFinite(num) ? num : null;
  }
  return null;
}

function toFileArray(value: any): File[] {
  if (typeof File === "undefined") return [];
  if (!value) return [];
  if (value instanceof File) return [value];
  if (typeof FileList !== "undefined" && value instanceof FileList) {
    return Array.from(value);
  }
  if (Array.isArray(value)) {
    return value.filter((item: any): item is File => item instanceof File);
  }
  return [];
}

type ConditionSpec = {
  equals?: any;
  notEquals?: any;
  in?: any[] | null;
  notIn?: any[] | null;
  truthy?: boolean;
};

function evaluateCondition(value: any, spec: ConditionSpec): boolean {
  let result = true;
  if ("equals" in spec) {
    result &&= value === spec.equals;
  }
  if ("notEquals" in spec) {
    result &&= value !== spec.notEquals;
  }
  if (spec.in) {
    result &&= spec.in.some((item) => item === value);
  }
  if (spec.notIn) {
    result &&= !spec.notIn.some((item) => item === value);
  }
  if ("truthy" in spec) {
    result &&= Boolean(value) === Boolean(spec.truthy);
  } else if (
    !("equals" in spec) &&
    !("notEquals" in spec) &&
    !spec.in &&
    !spec.notIn
  ) {
    result &&= Boolean(value);
  }
  return result;
}

function formatError(error: any, fallback: string) {
  return error ?? fallback;
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
      case "isUrl":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const input = String(value).trim();
          const hasProtocol = /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(input);
          try {
            const url = hasProtocol
              ? new URL(input)
              : new URL(`https://${input}`);
            if (spec.requireProtocol && !hasProtocol) {
              return formatError(spec.error, "URL must include a protocol");
            }
            if (spec.protocols && spec.protocols.length > 0) {
              const allowed = spec.protocols
                .filter(Boolean)
                .map((p) => p.replace(/:$/, "").toLowerCase());
              if (allowed.length > 0) {
                const protocol = url.protocol.replace(/:$/, "").toLowerCase();
                if (!allowed.includes(protocol)) {
                  const list = allowed.join(", ");
                  return formatError(
                    spec.error,
                    `URL must use protocol${allowed.length > 1 ? "s" : ""}: ${list}`
                  );
                }
              }
            }
            return null;
          } catch (_err) {
            return formatError(spec.error, "Must be a valid URL");
          }
        };
      case "isUUID":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const str = String(value).trim();
          const version = spec.version;
          const uuidPattern = version
            ? new RegExp(
                `^[0-9a-f]{8}-[0-9a-f]{4}-${version}[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`,
                "i"
              )
            : /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
          if (!uuidPattern.test(str)) {
            return formatError(
              spec.error,
              version
                ? `Must be a valid UUID v${version}`
                : "Must be a valid UUID"
            );
          }
          return null;
        };
      case "isULID":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const str = String(value).trim().toUpperCase();
          const ulidPattern = /^[0-9A-HJKMNP-TV-Z]{26}$/;
          if (!ulidPattern.test(str)) {
            return formatError(spec.error, "Must be a valid ULID");
          }
          return null;
        };
      case "isNumber":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const num = coerceNumber(value);
          if (num === null) {
            return formatError(spec.error, "Must be a number");
          }
          return null;
        };
      case "isInteger":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const num = coerceNumber(value);
          if (num === null || !Number.isInteger(num)) {
            return formatError(spec.error, "Must be an integer");
          }
          return null;
        };
      case "isDate":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const timestamp = coerceDate(value);
          if (timestamp === null) {
            return formatError(spec.error, "Must be a valid date");
          }
          return null;
        };
      case "isISODate":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          if (value instanceof Date) return null;
          const str = String(value).trim();
          const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
          const dateTimeRegex =
            /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(Z|[+-]\d{2}:\d{2})?$/;
          const matches = spec.withTime
            ? dateTimeRegex.test(str)
            : dateRegex.test(str);
          if (!matches) {
            return formatError(
              spec.error,
              spec.withTime
                ? "Must be an ISO-8601 datetime"
                : "Must be an ISO-8601 date"
            );
          }
          return null;
        };
      case "isBefore":
        return (value: any, values: any) => {
          const other =
            spec.field !== undefined
              ? getValueAtPath(values, spec.field)
              : spec.value;
          const left = coerceComparable(value);
          const right = coerceComparable(other);
          if (left === null || right === null) return null;
          const ok = spec.inclusive ? left <= right : left < right;
          if (!ok) {
            return formatError(spec.error, "Value must be before target");
          }
          return null;
        };
      case "isAfter":
        return (value: any, values: any) => {
          const other =
            spec.field !== undefined
              ? getValueAtPath(values, spec.field)
              : spec.value;
          const left = coerceComparable(value);
          const right = coerceComparable(other);
          if (left === null || right === null) return null;
          const ok = spec.inclusive ? left >= right : left > right;
          if (!ok) {
            return formatError(spec.error, "Value must be after target");
          }
          return null;
        };
      case "minItems":
        return (value: any) => {
          const arr = Array.isArray(value)
            ? value
            : typeof FileList !== "undefined" && value instanceof FileList
              ? Array.from(value)
              : null;
          const length = arr ? arr.length : value == null ? 0 : NaN;
          if (!arr || Number.isNaN(length) || length < spec.count) {
            return formatError(
              spec.error,
              spec.count === 1
                ? "Select at least one item"
                : `Select at least ${spec.count} items`
            );
          }
          return null;
        };
      case "maxItems":
        return (value: any) => {
          if (value == null) return null;
          const arr = Array.isArray(value)
            ? value
            : typeof FileList !== "undefined" && value instanceof FileList
              ? Array.from(value)
              : null;
          if (!arr) {
            return formatError(spec.error, "Value must be a list");
          }
          if (arr.length > spec.count) {
            return formatError(
              spec.error,
              `Select no more than ${spec.count} item${spec.count === 1 ? "" : "s"}`
            );
          }
          return null;
        };
      case "isArrayNotEmpty":
        return (value: any) => {
          const length = Array.isArray(value)
            ? value.length
            : typeof FileList !== "undefined" && value instanceof FileList
              ? value.length
              : 0;
          if (length === 0) {
            return formatError(spec.error, "At least one item is required");
          }
          return null;
        };
      case "allowedFileTypes":
        return (value: any) => {
          const files = toFileArray(value);
          if (files.length === 0) return null;
          const mimeRules = (spec.mimeTypes ?? [])
            .filter(Boolean)
            .map((m) => m.toLowerCase());
          const extRules = (spec.extensions ?? [])
            .filter(Boolean)
            .map((ext) => ext.replace(/^\./, "").toLowerCase());
          for (const file of files) {
            const mime = (file.type || "").toLowerCase();
            if (mimeRules.length > 0) {
              const matchesMime = mimeRules.some((rule) => {
                if (rule.endsWith("/*")) {
                  const prefix = rule.slice(0, -1);
                  return mime.startsWith(prefix);
                }
                return mime === rule;
              });
              if (!matchesMime) {
                return formatError(spec.error, "File type is not allowed");
              }
            }
            if (extRules.length > 0) {
              const name = file.name || "";
              const ext = name.includes(".")
                ? name.split(".").pop()!.toLowerCase()
                : "";
              if (!extRules.includes(ext)) {
                return formatError(spec.error, "File extension is not allowed");
              }
            }
          }
          return null;
        };
      case "maxFileSize":
        return (value: any) => {
          const files = toFileArray(value);
          if (files.length === 0) return null;
          for (const file of files) {
            if (file.size > spec.bytes) {
              return formatError(spec.error, "File is too large");
            }
          }
          return null;
        };
      case "requiredWhen":
        return (value: any, values: any) => {
          const other = getValueAtPath(values, spec.field);
          if (!evaluateCondition(other, spec)) return null;
          if (isEmptyValue(value)) {
            return formatError(spec.error, "This field is required");
          }
          return null;
        };
      case "requiredUnless":
        return (value: any, values: any) => {
          const other = getValueAtPath(values, spec.field);
          if (evaluateCondition(other, spec)) return null;
          if (isEmptyValue(value)) {
            return formatError(spec.error, "This field is required");
          }
          return null;
        };
      case "startsWith":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const subject = String(value);
          const target = spec.value;
          if (spec.caseSensitive === false) {
            if (!subject.toLowerCase().startsWith(target.toLowerCase())) {
              return formatError(spec.error, `Must start with ${target}`);
            }
          } else if (!subject.startsWith(target)) {
            return formatError(spec.error, `Must start with ${target}`);
          }
          return null;
        };
      case "endsWith":
        return (value: any) => {
          if (isEmptyValue(value)) return null;
          const subject = String(value);
          const target = spec.value;
          if (spec.caseSensitive === false) {
            if (!subject.toLowerCase().endsWith(target.toLowerCase())) {
              return formatError(spec.error, `Must end with ${target}`);
            }
          } else if (!subject.endsWith(target)) {
            return formatError(spec.error, `Must end with ${target}`);
          }
          return null;
        };
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
        console.log("Submitting:", {
          values,
          event,
          onSubmit: userOnSubmit,
          action,
        });
        event!.defaultPrevented = false;
        submitForm({ event: event!, onSubmit: userOnSubmit, action });
      }),
    [form, userOnSubmit]
  );

  const resetHandler = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
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
