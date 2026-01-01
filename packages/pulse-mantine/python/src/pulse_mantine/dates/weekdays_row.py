from typing import Any

import pulse as ps


@ps.react_component(ps.Import("WeekdaysRow", "pulse-mantine"))
def WeekdaysRow(key: str | None = None, **props: Any): ...
