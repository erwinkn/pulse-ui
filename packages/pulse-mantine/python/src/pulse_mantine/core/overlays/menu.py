import pulse as ps
from typing import Any


@ps.react_component("Menu", "@mantine/core")
def Menu(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Menu", "@mantine/core", prop="Item")
def MenuItem(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Menu", "@mantine/core", prop="Label")
def MenuLabel(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Menu", "@mantine/core", prop="Dropdown")
def MenuDropdown(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Menu", "@mantine/core", prop="Target")
def MenuTarget(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Menu", "@mantine/core", prop="Divider")
def MenuDivider(key: str | None = None, **props: Any): ...


@ps.react_component("Menu", "@mantine/core", prop="Sub")
def MenuSub(*children: ps.Child, key: str | None = None, **props: Any): ...
