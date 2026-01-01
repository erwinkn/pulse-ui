from typing import Any

import pulse as ps

_List = ps.Import("List", "@mantine/core")


@ps.react_component(_List)
def List(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_List.Item)
def ListItem(*children: ps.Node, key: str | None = None, **props: Any): ...
