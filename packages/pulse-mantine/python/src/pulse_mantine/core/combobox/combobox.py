import pulse as ps


@ps.react_component("Combobox", "@mantine/core")
def Combobox(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Target")
def ComboboxTarget(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Dropdown")
def ComboboxDropdown(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Options")
def ComboboxOptions(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Option")
def ComboboxOption(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Search")
def ComboboxSearch(key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Empty")
def ComboboxEmpty(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Chevron")
def ComboboxChevron(key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Footer")
def ComboboxFooter(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Header")
def ComboboxHeader(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="EventsTarget")
def ComboboxEventsTarget(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="DropdownTarget")
def ComboboxDropdownTarget(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="Group")
def ComboboxGroup(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="ClearButton")
def ComboboxClearButton(key: str | None = None, **props): ...


@ps.react_component("Combobox", "@mantine/core", prop="HiddenInput")
def ComboboxHiddenInput(key: str | None = None, **props): ...
