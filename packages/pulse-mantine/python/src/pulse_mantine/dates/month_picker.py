from typing import Any

import pulse as ps


@ps.react_component(ps.Import("MonthPicker", "pulse-mantine"))
def MonthPicker(key: str | None = None, **props: Any): ...
