from typing import Any

import pulse as ps


@ps.react_component(ps.Import("RadarChart", "@mantine/charts"))
def RadarChart(key: str | None = None, **props: Any): ...
