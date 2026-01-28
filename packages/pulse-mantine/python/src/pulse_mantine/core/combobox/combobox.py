from __future__ import annotations

from typing import Any, Literal, cast

import pulse as ps
from pulse.helpers import call_flexible, maybe_await
from pulse.scheduling import create_task

DropdownEventSource = Literal["keyboard", "mouse", "unknown"]
SelectedOptionTarget = Literal["active", "selected"]

_Combobox = ps.Import("Combobox", "@mantine/core")


@ps.react_component(ps.Import("Combobox", "pulse-mantine"))
def ComboboxInternal(
	*children: ps.Node,
	key: str | None = None,
	channelId: str | None = None,
	**props: Any,
): ...


class ComboboxStore(ps.State):
	_channel: ps.Channel
	_options: dict[str, Any]
	_on_opened_change: ps.EventHandler1[bool] | None
	_on_dropdown_open: ps.EventHandler1[DropdownEventSource] | None
	_on_dropdown_close: ps.EventHandler1[DropdownEventSource] | None

	def __init__(
		self,
		*,
		defaultOpened: bool | None = None,
		opened: bool | None = None,
		onOpenedChange: ps.EventHandler1[bool] | None = None,
		onDropdownOpen: ps.EventHandler1[DropdownEventSource] | None = None,
		onDropdownClose: ps.EventHandler1[DropdownEventSource] | None = None,
		loop: bool | None = None,
		scrollBehavior: Literal["auto", "smooth", "instant"] | None = None,
	) -> None:
		self._channel = ps.channel()
		self._options = {
			"defaultOpened": defaultOpened,
			"opened": opened,
			"loop": loop,
			"scrollBehavior": scrollBehavior,
		}
		self._options = {k: v for k, v in self._options.items() if v is not None}
		self._on_opened_change = onOpenedChange
		self._on_dropdown_open = onDropdownOpen
		self._on_dropdown_close = onDropdownClose

		self._channel.on("openedChange", self._handle_opened_change)
		self._channel.on("dropdownOpen", self._handle_dropdown_open)
		self._channel.on("dropdownClose", self._handle_dropdown_close)

	def open_dropdown(self, event_source: DropdownEventSource | None = None) -> None:
		payload = {"eventSource": event_source} if event_source is not None else None
		self._channel.emit("openDropdown", payload)

	def close_dropdown(self, event_source: DropdownEventSource | None = None) -> None:
		payload = {"eventSource": event_source} if event_source is not None else None
		self._channel.emit("closeDropdown", payload)

	def toggle_dropdown(self, event_source: DropdownEventSource | None = None) -> None:
		payload = {"eventSource": event_source} if event_source is not None else None
		self._channel.emit("toggleDropdown", payload)

	def select_option(self, index: int) -> None:
		if not isinstance(index, int):
			raise TypeError("index must be int")
		self._channel.emit("selectOption", {"index": index})

	def select_active_option(self) -> None:
		self._channel.emit("selectActiveOption")

	def select_first_option(self) -> None:
		self._channel.emit("selectFirstOption")

	def select_next_option(self) -> None:
		self._channel.emit("selectNextOption")

	def select_previous_option(self) -> None:
		self._channel.emit("selectPreviousOption")

	def reset_selected_option(self) -> None:
		self._channel.emit("resetSelectedOption")

	def click_selected_option(self) -> None:
		self._channel.emit("clickSelectedOption")

	def update_selected_option_index(
		self, target: SelectedOptionTarget | None = None
	) -> None:
		if target is not None and target not in ("active", "selected"):
			raise ValueError("target must be 'active' or 'selected'")
		payload = {"target": target} if target is not None else None
		self._channel.emit("updateSelectedOptionIndex", payload)

	def focus_search_input(self) -> None:
		self._channel.emit("focusSearchInput")

	def focus_target(self) -> None:
		self._channel.emit("focusTarget")

	def set_list_id(self, list_id: str) -> None:
		if not isinstance(list_id, str):
			raise TypeError("list_id must be str")
		self._channel.emit("setListId", {"listId": list_id})

	async def get_dropdown_opened(self) -> bool:
		result = await self._channel.request("getDropdownOpened")
		return bool(result)

	async def get_selected_option_index(self) -> int:
		result = await self._channel.request("getSelectedOptionIndex")
		if isinstance(result, bool):
			return -1
		return result if isinstance(result, int) else -1

	async def get_list_id(self) -> str | None:
		result = await self._channel.request("getListId")
		return result if isinstance(result, str) else None

	def render(
		self, *children: ps.Node, key: str | None = None, **props: Any
	) -> ps.Node:
		merged = {**self._options, **props}
		return ComboboxInternal(
			*children,
			key=key,
			channelId=self._channel.id,
			**merged,
		)

	async def _handle_opened_change(self, payload: Any) -> None:
		if not isinstance(payload, dict):
			return
		opened = payload.get("opened")
		if not isinstance(opened, bool):
			return
		listener = self._on_opened_change
		if listener is None:
			return
		create_task(maybe_await(call_flexible(listener, opened)))

	async def _handle_dropdown_open(self, payload: Any) -> None:
		source = _event_source_from_payload(payload)
		if source is None:
			return
		listener = self._on_dropdown_open
		if listener is None:
			return
		create_task(maybe_await(call_flexible(listener, source)))

	async def _handle_dropdown_close(self, payload: Any) -> None:
		source = _event_source_from_payload(payload)
		if source is None:
			return
		listener = self._on_dropdown_close
		if listener is None:
			return
		create_task(maybe_await(call_flexible(listener, source)))


def _event_source_from_payload(payload: Any) -> DropdownEventSource | None:
	if not isinstance(payload, dict):
		return None
	source = payload.get("eventSource")
	if isinstance(source, str) and source in {"keyboard", "mouse", "unknown"}:
		return cast(DropdownEventSource, source)
	return None


def _ComboboxWrapper(
	*children: ps.Node,
	key: str | None = None,
	store: ComboboxStore | None = None,
	**props: Any,
):
	if store is None:
		return ComboboxInternal(*children, key=key, channelId=None, **props)
	return store.render(*children, key=key, **props)


Combobox = _ComboboxWrapper


@ps.react_component(_Combobox.Target)
def ComboboxTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Dropdown)
def ComboboxDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Options)
def ComboboxOptions(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Option)
def ComboboxOption(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Search)
def ComboboxSearch(key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Empty)
def ComboboxEmpty(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Chevron)
def ComboboxChevron(key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Footer)
def ComboboxFooter(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.Header)
def ComboboxHeader(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.EventsTarget)
def ComboboxEventsTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.DropdownTarget)
def ComboboxDropdownTarget(
	*children: ps.Node, key: str | None = None, **props: Any
): ...


@ps.react_component(_Combobox.Group)
def ComboboxGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.ClearButton)
def ComboboxClearButton(key: str | None = None, **props: Any): ...


@ps.react_component(_Combobox.HiddenInput)
def ComboboxHiddenInput(key: str | None = None, **props: Any): ...
