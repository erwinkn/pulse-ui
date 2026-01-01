from typing import Any

import pulse as ps

_Timeline = ps.Import("Timeline", "@mantine/core")


@ps.react_component(_Timeline)
def Timeline(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Timeline.Item)
def TimelineItem(*children: ps.Node, key: str | None = None, **props: Any): ...
