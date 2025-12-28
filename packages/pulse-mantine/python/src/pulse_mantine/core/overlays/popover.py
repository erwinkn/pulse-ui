from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Popover", "@mantine/core"))
def Popover(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Popover", "@mantine/core", prop="Target"))
def PopoverTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Popover", "@mantine/core", prop="Dropdown"))
def PopoverDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...
