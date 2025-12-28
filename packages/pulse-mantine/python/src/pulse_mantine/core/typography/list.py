from typing import Any

import pulse as ps


@ps.react_component(ps.Import("List", "@mantine/core"))
def List(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("List", "@mantine/core", prop="Item"))
def ListItem(*children: ps.Node, key: str | None = None, **props: Any): ...
