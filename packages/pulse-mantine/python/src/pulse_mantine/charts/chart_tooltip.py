from typing import Any

import pulse as ps
from pulse.javascript_v2.imports import Import


@ps.react_component(
	"ChartTooltip",
	"@mantine/charts",
	extra_imports=[Import.css("@mantine/charts/styles.css")],
)
def ChartTooltip(key: str | None = None, **props: Any): ...
