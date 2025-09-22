from typing import Optional
import pulse as ps


@ps.react_component("ScrollArea", "@mantine/core")
def ScrollArea(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("ScrollArea", "@mantine/core", prop="Autosize")
def ScrollAreaAutosize(*children: ps.Child, key: Optional[str] = None, **props): ...

