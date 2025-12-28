from typing import Any

import pulse as ps


@ps.react_component(ps.Import("HoverCard", "@mantine/core"))
def HoverCard(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("HoverCard", "@mantine/core", prop="Target"))
def HoverCardTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("HoverCard", "@mantine/core", prop="Dropdown"))
def HoverCardDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("HoverCard", "@mantine/core", prop="Group"))
def HoverCardGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
