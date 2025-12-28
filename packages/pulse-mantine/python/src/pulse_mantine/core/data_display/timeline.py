from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Timeline", "@mantine/core"))
def Timeline(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Timeline", "@mantine/core", prop="Item"))
def TimelineItem(*children: ps.Node, key: str | None = None, **props: Any): ...
