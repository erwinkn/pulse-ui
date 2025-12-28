from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ScatterChart", "@mantine/charts"))
def ScatterChart(key: str | None = None, **props: Any): ...
