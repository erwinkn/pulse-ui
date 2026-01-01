from typing import Any

import pulse as ps


@ps.react_component(ps.Import("PieChart", "@mantine/charts"))
def PieChart(key: str | None = None, **props: Any): ...
