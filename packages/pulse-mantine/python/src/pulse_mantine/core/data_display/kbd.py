from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Kbd", "@mantine/core"))
def Kbd(*children: ps.Node, key: str | None = None, **props: Any): ...
