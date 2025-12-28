from typing import Any

import pulse as ps


@ps.react_component(ps.Import("CompositeChart", "@mantine/charts"))
def CompositeChart(key: str | None = None, **props: Any): ...
