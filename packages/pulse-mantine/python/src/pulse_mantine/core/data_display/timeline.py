from typing import Any

import pulse as ps


@ps.react_component("Timeline", "@mantine/core")
def Timeline(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Timeline", "@mantine/core", prop="Item")
def TimelineItem(*children: ps.Child, key: str | None = None, **props: Any): ...
