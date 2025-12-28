from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Sparkline", "@mantine/charts"))
def Sparkline(key: str | None = None, **props: Any): ...
