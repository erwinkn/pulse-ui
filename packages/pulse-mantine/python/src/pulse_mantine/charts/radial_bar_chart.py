from typing import Any

import pulse as ps


@ps.react_component(ps.Import("RadialBarChart", "@mantine/charts"))
def RadialBarChart(key: str | None = None, **props: Any): ...
