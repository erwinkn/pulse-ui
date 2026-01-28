import { Combobox as MantineCombobox, useCombobox } from "@mantine/core";
import { usePulseChannel } from "pulse-ui-client";
import { type ComponentPropsWithoutRef, useEffect } from "react";

type DropdownEventSource = "keyboard" | "mouse" | "unknown";

type SelectedOptionTarget = "active" | "selected";

type ComboboxScrollBehavior = ScrollBehavior | "instant";

export interface PulseComboboxProps
	extends Omit<ComponentPropsWithoutRef<typeof MantineCombobox>, "store"> {
	channelId?: string;
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
	// biome-ignore lint/correctness/useHookAtTopLevel: channelId is not expected to change
	const channel = channelId ? usePulseChannel(channelId) : undefined;

	const combobox = useCombobox({
		defaultOpened,
		opened,
		onOpenedChange: (nextOpened) => {
			onOpenedChange?.(nextOpened);
			channel?.emit("openedChange", { opened: nextOpened });
		},
		onDropdownOpen: (eventSource) => {
			onDropdownOpen?.(eventSource);
			channel?.emit("dropdownOpen", { eventSource });
		},
		onDropdownClose: (eventSource) => {
			onDropdownClose?.(eventSource);
			channel?.emit("dropdownClose", { eventSource });
		},
		loop,
		scrollBehavior
	});

	useEffect(() => {
		if (!channel) return;

		const cleanups = [
			channel.on("openDropdown", (payload?: { eventSource?: DropdownEventSource }) => {
				combobox.openDropdown(payload?.eventSource);
			}),
			channel.on("closeDropdown", (payload?: { eventSource?: DropdownEventSource }) => {
				combobox.closeDropdown(payload?.eventSource);
			}),
			channel.on("toggleDropdown", (payload?: { eventSource?: DropdownEventSource }) => {
				combobox.toggleDropdown(payload?.eventSource);
			}),
			channel.on("selectOption", (payload?: { index?: number }) => {
				if (!payload || typeof payload.index !== "number") return;
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
				(payload?: { target?: SelectedOptionTarget }) => {
					combobox.updateSelectedOptionIndex(payload?.target);
				},
			),
			channel.on("focusSearchInput", () => {
				combobox.focusSearchInput();
			}),
			channel.on("focusTarget", () => {
				combobox.focusTarget();
			}),
			channel.on("setListId", (payload?: { listId?: string }) => {
				if (!payload || typeof payload.listId !== "string") return;
				combobox.setListId(payload.listId);
			}),
			channel.on("getDropdownOpened", () => combobox.dropdownOpened),
			channel.on("getSelectedOptionIndex", () => combobox.selectedOptionIndex),
			channel.on("getListId", () => combobox.listId),
		];

		return () => {
			for (const dispose of cleanups) dispose();
		};
	}, [channel, combobox]);

	return <MantineCombobox {...(rest as any)} store={combobox} />;
}
