from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Collapse", "@mantine/core"))
def Collapse(*children: ps.Node, key: str | None = None, **props: Any): ...
