from typing import Any

import pulse as ps


@ps.react_component(ps.Import("YearPicker", "pulse-mantine"))
def YearPicker(key: str | None = None, **props: Any): ...
