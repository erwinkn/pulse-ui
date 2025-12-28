from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Slider", "pulse-mantine"))
def Slider(*children: ps.Node, key: str | None = None, **props: Any): ...
