from typing import Any

import pulse as ps


@ps.react_component(ps.Import("SegmentedControl", "pulse-mantine"))
def SegmentedControl(*children: ps.Node, key: str | None = None, **props: Any): ...
