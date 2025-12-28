from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Combobox", "@mantine/core"))
def Combobox(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Target"))
def ComboboxTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Dropdown"))
def ComboboxDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Options"))
def ComboboxOptions(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Option"))
def ComboboxOption(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Search"))
def ComboboxSearch(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Empty"))
def ComboboxEmpty(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Chevron"))
def ComboboxChevron(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Footer"))
def ComboboxFooter(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Header"))
def ComboboxHeader(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="EventsTarget"))
def ComboboxEventsTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="DropdownTarget"))
def ComboboxDropdownTarget(
	*children: ps.Node, key: str | None = None, **props: Any
): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="Group"))
def ComboboxGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="ClearButton"))
def ComboboxClearButton(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Combobox", "@mantine/core", prop="HiddenInput"))
def ComboboxHiddenInput(key: str | None = None, **props: Any): ...
