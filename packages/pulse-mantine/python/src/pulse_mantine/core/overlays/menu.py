from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Menu", "@mantine/core"))
def Menu(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Menu", "@mantine/core", prop="Item"))
def MenuItem(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Menu", "@mantine/core", prop="Label"))
def MenuLabel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Menu", "@mantine/core", prop="Dropdown"))
def MenuDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Menu", "@mantine/core", prop="Target"))
def MenuTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Menu", "@mantine/core", prop="Divider"))
def MenuDivider(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Menu", "@mantine/core", prop="Sub"))
def MenuSub(*children: ps.Node, key: str | None = None, **props: Any): ...
