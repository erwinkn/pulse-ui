from typing import Any

import pulse as ps

_Combobox = ps.Import("Combobox", "@mantine/core")


@ps.react_component(_Combobox)
def Combobox(*children: ps.Node, key: str | None = None, **props: Any): ...


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
