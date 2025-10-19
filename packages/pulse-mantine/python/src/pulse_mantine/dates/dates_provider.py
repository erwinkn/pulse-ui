import pulse as ps
from pulse.codegen.imports import ImportStatement


@ps.react_component(
	"DatesProvider",
	"pulse-mantine",
	extra_imports=[ImportStatement(src="@mantine/dates/styles.css", side_effect=True)],
)
def DatesProvider(*children: ps.Child, key: str | None = None, **props): ...
