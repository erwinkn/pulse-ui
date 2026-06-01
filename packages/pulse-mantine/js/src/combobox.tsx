import { Combobox as MantineCombobox, useCombobox } from "@mantine/core";
import { usePulseChannel, type ChannelBridge } from "pulse-ui-client";
import { type ComponentPropsWithoutRef, useEffect, useRef } from "react";

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
	const channel = usePulseChannel(channelId);
	const channelRef = useRef<ChannelBridge | null>(null);

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

	useEffect(() => {
		if (!channel) return;
		channelRef.current = channel;
		const cleanups = [
			channel.on("openDropdown", (payload: OptionalEventSourcePayload) => {
				combobox.openDropdown(payload?.eventSource);
			}),
			channel.on("closeDropdown", (payload: OptionalEventSourcePayload) => {
				combobox.closeDropdown(payload?.eventSource);
			}),
			channel.on("toggleDropdown", (payload: OptionalEventSourcePayload) => {
				combobox.toggleDropdown(payload?.eventSource);
			}),
			channel.on("selectOption", (payload: { index: number }) => {
				combobox.selectOption(payload.index);
			}),
			channel.on("selectActiveOption", () => combobox.selectActiveOption()),
			channel.on("selectFirstOption", () => combobox.selectFirstOption()),
			channel.on("selectNextOption", () => combobox.selectNextOption()),
			channel.on("selectPreviousOption", () => combobox.selectPreviousOption()),
			channel.on("resetSelectedOption", () => {
				combobox.resetSelectedOption();
			}),
			channel.on("clickSelectedOption", () => {
				combobox.clickSelectedOption();
			}),
			channel.on(
				"updateSelectedOptionIndex",
				(payload: OptionalTargetPayload) => {
					combobox.updateSelectedOptionIndex(payload?.target);
				},
			),
			channel.on("focusSearchInput", () => {
				combobox.focusSearchInput();
			}),
			channel.on("focusTarget", () => {
				combobox.focusTarget();
			}),
			channel.on("setListId", (payload: { listId: string }) => {
				combobox.setListId(payload.listId);
			}),
			channel.on("getDropdownOpened", () => combobox.dropdownOpened),
			channel.on("getSelectedOptionIndex", () => combobox.selectedOptionIndex),
			channel.on("getListId", () => combobox.listId),
		];

		return () => {
			for (const dispose of cleanups) dispose();
			if (channelRef.current === channel) {
				channelRef.current = null;
			}
		};
	}, [channel, combobox]);

	return <MantineCombobox {...(rest as any)} store={combobox} />;
}
