from typing import Any

import pulse as ps


@ps.react_component(ps.Import("MiniCalendar", "pulse-mantine"))
def MiniCalendar(key: str | None = None, **props: Any): ...
