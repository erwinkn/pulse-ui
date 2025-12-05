from typing import Any

import pulse as ps
from pulse.javascript.imports import CssImport


@ps.react_component(
	"ChartTooltip",
	"@mantine/charts",
	extra_imports=[CssImport("@mantine/charts/styles.css")],
)
def ChartTooltip(key: str | None = None, **props: Any): ...
