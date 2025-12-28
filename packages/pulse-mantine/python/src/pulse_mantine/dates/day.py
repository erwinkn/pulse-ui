from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Day", "pulse-mantine"))
def Day(key: str | None = None, **props: Any): ...
