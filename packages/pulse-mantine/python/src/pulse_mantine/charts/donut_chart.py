from typing import Any

import pulse as ps


@ps.react_component(ps.Import("DonutChart", "@mantine/charts"))
def DonutChart(key: str | None = None, **props: Any): ...
