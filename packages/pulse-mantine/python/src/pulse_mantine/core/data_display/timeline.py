from typing import Optional
import pulse as ps


@ps.react_component("Timeline", "@mantine/core")
def Timeline(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Timeline", "@mantine/core", prop="Item")
def TimelineItem(*children: ps.Child, key: Optional[str] = None, **props): ...

