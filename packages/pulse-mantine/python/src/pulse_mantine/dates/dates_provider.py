from typing import Optional
import pulse as ps
from pulse.codegen.imports import ImportStatement


@ps.react_component(
    "DatesProvider",
    "@mantine/dates",
    extra_imports=[ImportStatement(src="@mantine/dates/styles.css", side_effect=True)],
)
def DatesProvider(*children: ps.Child, key: Optional[str] = None, **props): ...
