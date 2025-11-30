from typing import Any

import pulse as ps
from pulse.javascript_v2.imports import Import


@ps.react_component(
	"DatesProvider",
	"pulse-mantine",
	extra_imports=[Import.css("@mantine/dates/styles.css")],
)
def DatesProvider(*children: ps.Child, key: str | None = None, **props: Any): ...
