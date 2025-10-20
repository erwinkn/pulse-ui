import pulse as ps
from typing import Any


@ps.react_component("Popover", "@mantine/core")
def Popover(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Popover", "@mantine/core", prop="Target")
def PopoverTarget(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Popover", "@mantine/core", prop="Dropdown")
def PopoverDropdown(*children: ps.Child, key: str | None = None, **props: Any): ...
