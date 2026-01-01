from typing import Any

import pulse as ps

_ScrollArea = ps.Import("ScrollArea", "@mantine/core")


@ps.react_component(_ScrollArea)
def ScrollArea(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_ScrollArea.Autosize)
def ScrollAreaAutosize(*children: ps.Node, key: str | None = None, **props: Any): ...
