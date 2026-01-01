from typing import Any

import pulse as ps


@ps.react_component(ps.Import("BubbleChart", "@mantine/charts"))
def BubbleChart(key: str | None = None, **props: Any): ...
