from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Anchor", "@mantine/core"))
def Anchor(*children: ps.Node, key: str | None = None, **props: Any): ...
