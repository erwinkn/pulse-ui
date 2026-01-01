from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Skeleton", "@mantine/core"))
def Skeleton(*children: ps.Node, key: str | None = None, **props: Any): ...
