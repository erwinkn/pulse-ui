from typing import Any

import pulse as ps

_Popover = ps.Import("Popover", "@mantine/core")


@ps.react_component(_Popover)
def Popover(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Popover.Target)
def PopoverTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Popover.Dropdown)
def PopoverDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...
