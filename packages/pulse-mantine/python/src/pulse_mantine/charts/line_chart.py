from typing import Any

import pulse as ps


@ps.react_component(ps.Import("LineChart", "@mantine/charts"))
def LineChart(key: str | None = None, **props: Any): ...
