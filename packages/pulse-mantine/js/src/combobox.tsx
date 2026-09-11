import { Combobox as MantineCombobox, useCombobox } from "@mantine/core";
import { useChannel } from "pulse-ui-client";
import { type ComponentPropsWithoutRef, useEffect, useLayoutEffect, useRef } from "react";

type DropdownEventSource = "keyboard" | "mouse" | "unknown";

type SelectedOptionTarget = "active" | "selected";

type ComboboxScrollBehavior = ScrollBehavior | "instant";

type OptionalEventSourcePayload =
	| { eventSource?: DropdownEventSource }
	| null
	| undefined;

type OptionalTargetPayload = { target?: SelectedOptionTarget } | null | undefined;

export interface PulseComboboxProps
	extends Omit<ComponentPropsWithoutRef<typeof MantineCombobox>, "store"> {
	channelId: string;
	defaultOpened?: boolean;
	opened?: boolean;
	onOpenedChange?: (opened: boolean) => void;
	onDropdownOpen?: (eventSource: DropdownEventSource) => void;
	onDropdownClose?: (eventSource: DropdownEventSource) => void;
	loop?: boolean;
	scrollBehavior?: ComboboxScrollBehavior;
}

export function Combobox({
	channelId,
	defaultOpened,
	opened,
	onOpenedChange,
	onDropdownOpen,
	onDropdownClose,
	loop,
	scrollBehavior,
	...rest
}: PulseComboboxProps) {
	const channel = useChannel(channelId);
	const channelRef = useRef(channel);
	useLayoutEffect(() => {
		channelRef.current = channel;
	}, [channel]);

	const combobox = useCombobox({
		defaultOpened,
		opened,
		onOpenedChange: (nextOpened) => {
			onOpenedChange?.(nextOpened);
			channelRef.current?.emit("openedChange", { opened: nextOpened });
		},
		onDropdownOpen: (eventSource) => {
			onDropdownOpen?.(eventSource);
			channelRef.current?.emit("dropdownOpen", { eventSource });
		},
		onDropdownClose: (eventSource) => {
			onDropdownClose?.(eventSource);
			channelRef.current?.emit("dropdownClose", { eventSource });
		},
		loop,
		scrollBehavior,
	});
	const comboboxRef = useRef(combobox);
	const listIdRef = useRef<string | undefined>(undefined);
	useLayoutEffect(() => {
		comboboxRef.current = combobox;
	});

	useEffect(() => {
		const cleanups = [
			channel.on("openDropdown", (payload: OptionalEventSourcePayload) => {
				comboboxRef.current.openDropdown(payload?.eventSource);
			}),
			channel.on("closeDropdown", (payload: OptionalEventSourcePayload) => {
				comboboxRef.current.closeDropdown(payload?.eventSource);
			}),
			channel.on("toggleDropdown", (payload: OptionalEventSourcePayload) => {
				comboboxRef.current.toggleDropdown(payload?.eventSource);
			}),
			channel.on("selectOption", (payload: { index: number }) => {
				comboboxRef.current.selectOption(payload.index);
			}),
			channel.on("selectActiveOption", () => comboboxRef.current.selectActiveOption()),
			channel.on("selectFirstOption", () => comboboxRef.current.selectFirstOption()),
			channel.on("selectNextOption", () => comboboxRef.current.selectNextOption()),
			channel.on("selectPreviousOption", () => comboboxRef.current.selectPreviousOption()),
			channel.on("resetSelectedOption", () => {
				comboboxRef.current.resetSelectedOption();
			}),
			channel.on("clickSelectedOption", () => {
				comboboxRef.current.clickSelectedOption();
			}),
			channel.on(
				"updateSelectedOptionIndex",
				(payload: OptionalTargetPayload) => {
					comboboxRef.current.updateSelectedOptionIndex(payload?.target);
				},
			),
			channel.on("focusSearchInput", () => comboboxRef.current.focusSearchInput()),
			channel.on("focusTarget", () => comboboxRef.current.focusTarget()),
			channel.on("setListId", (payload: { listId: string }) => {
				listIdRef.current = payload.listId;
				comboboxRef.current.setListId(payload.listId);
			}),
			channel.on("getDropdownOpened", () => comboboxRef.current.dropdownOpened),
			channel.on("getSelectedOptionIndex", () => comboboxRef.current.getSelectedOptionIndex()),
			// Mantine has no getListId(); setListId mutates a ref without rerender.
			channel.on("getListId", () => listIdRef.current ?? comboboxRef.current.listId),
		];

		return () => {
			for (const dispose of cleanups) dispose();
		};
	}, [channel]);

	return <MantineCombobox {...(rest as any)} store={combobox} />;
}
