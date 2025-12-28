from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ChartLegend", "@mantine/charts"))
def ChartLegend(key: str | None = None, **props: Any): ...
