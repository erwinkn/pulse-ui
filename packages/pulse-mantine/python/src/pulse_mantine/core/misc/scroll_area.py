from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ScrollArea", "@mantine/core"))
def ScrollArea(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("ScrollArea", "@mantine/core", prop="Autosize"))
def ScrollAreaAutosize(*children: ps.Node, key: str | None = None, **props: Any): ...
