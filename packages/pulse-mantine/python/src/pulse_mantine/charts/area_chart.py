from typing import Any

import pulse as ps


@ps.react_component(ps.Import("AreaChart", "@mantine/charts"))
def AreaChart(key: str | None = None, **props: Any): ...
