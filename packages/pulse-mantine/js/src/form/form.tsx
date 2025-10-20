import type { UseFormInput, UseFormReturnType } from "@mantine/form";
import { useForm } from "@mantine/form";
import { serialize, submitForm, usePulseChannel } from "pulse-ui-client";
import {
	type ComponentPropsWithoutRef,
	type FormEvent,
	type ReactNode,
	useCallback,
	useEffect,
	useMemo,
	useRef,
} from "react";
import { FormProvider } from "./context";
import { isValidatorSchema, splitValidationSchema, type ValidatorSchema } from "./validators";

type SyncMode = "none" | "blur" | "change";

export interface MantineFormProps<TValues = any> extends ComponentPropsWithoutRef<"form"> {
	channelId: string;
	children?: ReactNode;
	/** Initial values/errors/dirty/touched passed to useForm */
	initialValues?: UseFormInput<TValues>["initialValues"];
	initialErrors?: UseFormInput<TValues>["initialErrors"];
	initialDirty?: UseFormInput<TValues>["initialDirty"];
	initialTouched?: UseFormInput<TValues>["initialTouched"];
	/** Mantine useForm options */
	mode?: "controlled" | "uncontrolled";
	touchTrigger?: "focus" | "change";
	/** Serialized validation spec */
	validate?: ValidatorSchema;
	validateInputOnBlur?: boolean | string[];
	validateInputOnChange?: boolean | string[];
	clearInputErrorOnChange?: boolean;
	cascadeUpdates?: boolean;
	/** Sync mode: none, blur, or change */
	syncMode?: SyncMode;
	debounceMs?: number;
}

export function Form<TValues extends Record<string, any> = Record<string, any>>({
	children,
	action,
	channelId,
	validate,
	initialValues,
	initialErrors,
	initialDirty,
	initialTouched,
	mode = "controlled",
	touchTrigger,
	validateInputOnBlur,
	validateInputOnChange,
	clearInputErrorOnChange,
	debounceMs = 300,
	syncMode = "none",
	onSubmit: userOnSubmit,
	onReset: userOnReset,
	cascadeUpdates,
	...formProps
}: MantineFormProps<TValues>) {
	const channel = usePulseChannel(channelId);
	const formRef = useRef<UseFormReturnType<TValues> | null>(null);
	// Timers for server-validation per path
	const serverTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
	useForm({
		validate: { path: () => new Promise<string>((resolve) => resolve("")) },
	});
	// Timers for change-sync per path
	const syncTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
	// Ensure positive debounce delay
	debounceMs = Math.max(0, debounceMs ?? 0);

	const { clientRules, serverRulesByPath } = useMemo(() => {
		if (validate && isValidatorSchema(validate)) {
			return splitValidationSchema(validate);
		}
		// Satisfies first, to make sure our casting isn't abusive
		return {
			clientRules: {},
			serverRulesByPath: {},
		} satisfies ReturnType<typeof splitValidationSchema> as ReturnType<
			typeof splitValidationSchema
		>;
	}, [validate]);

	const sendSync = useCallback(
		(reason: "change" | "blur", path?: string) => {
			const values = formRef.current?.getValues();
			if (!values) return;
			channel.emit("syncValues", { reason, path, values });
		},
		[channel],
	);

	const getValueAtPath = useCallback((source: any, path?: string) => {
		if (!source || !path) return undefined;
		return String(path)
			.split(".")
			.reduce((acc: any, key: string) => (acc == null ? undefined : acc[key]), source);
	}, []);

	const shouldValidateOnChange = useCallback(
		(path: string) => {
			const v = validateInputOnChange;
			if (v === true) return true;
			if (Array.isArray(v)) return v.includes(path);
			return false;
		},
		[validateInputOnChange],
	);

	const shouldValidateOnBlur = useCallback(
		(path: string) => {
			const v = validateInputOnBlur;
			if (v === true) return true;
			if (Array.isArray(v)) return v.includes(path);
			return false;
		},
		[validateInputOnBlur],
	);

	const serverOnChange = useCallback(
		(path: string, debounce: boolean) => {
			const values = formRef.current?.getValues();
			if (!values) {
				return;
			}

			// Value syncing on change
			if (syncMode === "change") {
				const existing = syncTimersRef.current.get(path);
				if (existing) {
					clearTimeout(existing);
					syncTimersRef.current.delete(path);
				}
				const delay = debounce ? debounceMs : 0;
				if (delay > 0) {
					const handle = setTimeout(() => {
						syncTimersRef.current.delete(path);
						sendSync("change", path);
					}, delay);
					syncTimersRef.current.set(path, handle);
				} else {
					sendSync("change", path);
				}
			}

			// Server validation on change
			const serverRules = serverRulesByPath[path];
			const hasServerValidation = Array.isArray(serverRules) && serverRules.length > 0;
			if (!hasServerValidation) return;

			// Override form-level gating when any rule explicitly sets runOn="change"
			const explicitChange = serverRules.some((r: any) => r?.runOn === "change");
			const shouldRunChange = explicitChange || shouldValidateOnChange(path);
			if (!shouldRunChange) return;

			// Choose eligible rules: if explicitChange, only those; else those without runOn
			const changeEligible = explicitChange
				? serverRules.filter((r: any) => r?.runOn === "change")
				: serverRules.filter((r: any) => !r?.runOn);
			if (changeEligible.length === 0) return;

			const specified = changeEligible
				.map((r) => (typeof r?.debounceMs === "number" ? r.debounceMs : undefined))
				.filter((n): n is number => typeof n === "number");

			// If any rule specifies debounceMs, use the max; else use component default when debounce==true
			const ruleDelay = specified.length > 0 ? Math.max(...specified) : debounce ? debounceMs : 0;

			const timers = serverTimersRef.current;
			const existingTimer = timers.get(path);
			if (existingTimer) {
				clearTimeout(existingTimer);
				timers.delete(path);
			}
			timers.set(
				path,
				setTimeout(
					() => {
						timers.delete(path);
						const latestValues = formRef.current?.getValues();
						if (!latestValues) return;
						const value = getValueAtPath(latestValues, path);
						channel.emit("serverValidate", {
							value,
							values: latestValues,
							path,
						});
					},
					Math.max(0, ruleDelay),
				),
			);
		},
		[
			debounceMs,
			getValueAtPath,
			syncMode,
			sendSync,
			serverRulesByPath,
			shouldValidateOnChange,
			channel,
		],
	);

	const serverOnBlur = useCallback(
		(path: string) => {
			const values = formRef.current?.getValues();
			if (!values) return;

			// Flush any pending change sync immediately
			const pending = syncTimersRef.current.get(path);
			if (pending) {
				clearTimeout(pending);
				syncTimersRef.current.delete(path);
				sendSync("change", path);
			}

			// Sync current values on blur if configured
			if (syncMode === "blur") {
				sendSync("blur", path);
			}

			// Server validation on blur (no debounce)
			const serverRules = serverRulesByPath[path];
			const hasServerValidation = Array.isArray(serverRules) && serverRules.length > 0;
			if (!hasServerValidation) return;

			// Override form-level gating when any rule explicitly sets runOn="blur"
			const explicitBlur = serverRules.some((r: any) => r?.runOn === "blur");
			const shouldRunBlur = explicitBlur || shouldValidateOnBlur(path);
			if (!shouldRunBlur) return;

			// Choose eligible rules: if explicitBlur, only those; else those without runOn
			const blurEligible = explicitBlur
				? serverRules.filter((r: any) => r?.runOn === "blur")
				: serverRules.filter((r: any) => !r?.runOn);
			if (blurEligible.length === 0) return;
			const timers = serverTimersRef.current;
			const existingTimer = timers.get(path);
			if (existingTimer) {
				clearTimeout(existingTimer);
				timers.delete(path);
			}
			const latestValues = formRef.current?.getValues();
			if (!latestValues) return;
			const value = getValueAtPath(latestValues, path);
			channel.emit("serverValidate", { value, values: latestValues, path });
		},
		[getValueAtPath, syncMode, sendSync, serverRulesByPath, shouldValidateOnBlur, channel],
	);

	const form = useForm<any>({
		mode,
		touchTrigger,
		validate: clientRules,
		initialValues: initialValues,
		initialErrors: initialErrors,
		initialDirty: initialDirty,
		initialTouched: initialTouched,
		validateInputOnBlur,
		validateInputOnChange,
		clearInputErrorOnChange,
		onSubmitPreventDefault: "always",
		cascadeUpdates,
	});
	formRef.current = form;

	// Cleanup outstanding timers on unmount
	useEffect(() => {
		return () => {
			serverTimersRef.current.forEach((t: ReturnType<typeof setTimeout>) => {
				clearTimeout(t);
			});
			serverTimersRef.current.clear();
			syncTimersRef.current.forEach((t) => {
				clearTimeout(t);
			});
			syncTimersRef.current.clear();
		};
	}, []);

	useEffect(() => {
		const cleanups = [
			channel.on("setValues", (payload: { values: TValues }) => {
				if (payload?.values !== undefined) {
					form.setValues(payload.values);
					// Always sync back after programmatic value updates
					sendSync("change");
				}
			}),
			channel.on("setFieldValue", (payload: { path: string; value: any }) => {
				if (!payload) return;
				form.setFieldValue(payload.path, payload.value);
				sendSync("change", payload.path);
			}),
			channel.on("insertListItem", (payload: { path: string; item: any; index?: number }) => {
				if (!payload) return;
				form.insertListItem(payload.path, payload.item, payload.index);
				sendSync("change", payload.path);
			}),
			channel.on("removeListItem", (payload: { path: string; index: number }) => {
				if (!payload) return;
				form.removeListItem(payload.path, payload.index);
				sendSync("change", payload.path);
			}),
			channel.on("reorderListItem", (payload: { path: string; from: number; to: number }) => {
				if (!payload) return;
				form.reorderListItem(payload.path, {
					from: payload.from,
					to: payload.to,
				});
				sendSync("change", payload.path);
			}),
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
					paths.forEach((p) => {
						form.clearFieldError(p);
					});
				} else {
					form.clearErrors();
				}
			}),
			channel.on("setTouched", (payload: { touched: Record<string, boolean> }) => {
				if (!payload) return;
				form.setTouched(payload.touched);
			}),
			channel.on("validate", () => {
				// Client-side validation of all fields. Server-side validation is triggered on Python side.
				form.validate();
			}),
			channel.on("reset", (payload?: { initialValues?: TValues }) => {
				if (payload?.initialValues) {
					// Same behavior as form.reset(), except we allow modifying the initialValues
					form.resetTouched();
					form.resetDirty();
					form.setValues(payload.initialValues);
					sendSync("change");
				} else {
					form.reset();
					sendSync("change");
				}
			}),
			channel.on("getFormValues", () => form.getValues()),
		];

		return () => {
			for (const dispose of cleanups) dispose();
		};
	}, [channel, form, sendSync]);

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

				const actionUrl = typeof action === "string" ? action : undefined;
				submitForm({
					event: event!,
					onSubmit: userOnSubmit,
					action: actionUrl ?? "",
					formData,
					// Mantine will have already called event.preventDefault(), we want to ignore that
					force: true,
				});
			}),
		[form, userOnSubmit, action],
	);

	const resetHandler = useCallback(
		(event: FormEvent<HTMLFormElement>) => {
			userOnReset?.(event);
			form.onReset(event);
		},
		[form, userOnReset],
	);

	return (
		<FormProvider form={form} serverOnChange={serverOnChange} serverOnBlur={serverOnBlur}>
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
				const value = visit(node[key], childPath);
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
