from typing import Any

import pulse as ps


@ps.react_component(
	ps.Import("DatesProvider", "pulse-mantine"),
)
def DatesProvider(*children: ps.Node, key: str | None = None, **props: Any): ...
