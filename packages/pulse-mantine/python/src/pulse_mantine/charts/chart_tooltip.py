import pulse as ps
from pulse.codegen.imports import ImportStatement


@ps.react_component(
	"ChartTooltip",
	"@mantine/charts",
	extra_imports=[ImportStatement(src="@mantine/charts/styles.css", side_effect=True)],
)
def ChartTooltip(key: str | None = None, **props): ...
