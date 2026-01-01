from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Indicator", "@mantine/core"))
def Indicator(*children: ps.Node, key: str | None = None, **props: Any): ...
