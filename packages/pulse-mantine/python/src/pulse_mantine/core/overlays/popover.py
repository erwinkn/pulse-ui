from typing import Optional
import pulse as ps


@ps.react_component("Popover", "@mantine/core")
def Popover(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Popover", "@mantine/core", prop="Target")
def PopoverTarget(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Popover", "@mantine/core", prop="Dropdown")
def PopoverDropdown(*children: ps.Child, key: Optional[str] = None, **props): ...

