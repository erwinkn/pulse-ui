from typing import Any

import pulse as ps


@ps.react_component("ScrollArea", "@mantine/core")
def ScrollArea(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("ScrollArea", "@mantine/core", prop="Autosize")
def ScrollAreaAutosize(*children: ps.Child, key: str | None = None, **props: Any): ...
