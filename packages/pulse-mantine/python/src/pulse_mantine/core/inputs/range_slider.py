from typing import Any

import pulse as ps


@ps.react_component(ps.Import("RangeSlider", "pulse-mantine"))
def RangeSlider(*children: ps.Node, key: str | None = None, **props: Any): ...
