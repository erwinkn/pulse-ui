from typing import Any

import pulse as ps


@ps.react_component(
	ps.Import("ChartTooltip", "@mantine/charts"),
)
def ChartTooltip(key: str | None = None, **props: Any): ...
