from typing import Any

import pulse as ps

_Menu = ps.Import("Menu", "@mantine/core")


@ps.react_component(_Menu)
def Menu(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Menu.Item)
def MenuItem(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Menu.Label)
def MenuLabel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Menu.Dropdown)
def MenuDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Menu.Target)
def MenuTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Menu.Divider)
def MenuDivider(key: str | None = None, **props: Any): ...


@ps.react_component(_Menu.Sub)
def MenuSub(*children: ps.Node, key: str | None = None, **props: Any): ...
