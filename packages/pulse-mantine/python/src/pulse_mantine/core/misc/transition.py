from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Transition", "@mantine/core"))
def Transition(*children: ps.Node, key: str | None = None, **props: Any): ...
