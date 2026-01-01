from typing import Any

import pulse as ps


@ps.react_component(ps.Import("TimeGrid", "pulse-mantine"))
def TimeGrid(key: str | None = None, **props: Any): ...
