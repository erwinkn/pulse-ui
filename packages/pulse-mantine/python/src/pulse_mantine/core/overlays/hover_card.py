from typing import Any

import pulse as ps

_HoverCard = ps.Import("HoverCard", "@mantine/core")


@ps.react_component(_HoverCard)
def HoverCard(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_HoverCard.Target)
def HoverCardTarget(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_HoverCard.Dropdown)
def HoverCardDropdown(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_HoverCard.Group)
def HoverCardGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
