from typing import Any

import pulse as ps


@ps.react_component(ps.Import("FunnelChart", "@mantine/charts"))
def FunnelChart(key: str | None = None, **props: Any): ...
