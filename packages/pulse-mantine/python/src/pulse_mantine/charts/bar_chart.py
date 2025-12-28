from typing import Any

import pulse as ps


@ps.react_component(ps.Import("BarChart", "@mantine/charts"))
def BarChart(key: str | None = None, **props: Any): ...
