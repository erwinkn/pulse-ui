from typing import Any

import pulse as ps


@ps.react_component(ps.Import("YearPickerInput", "pulse-mantine"))
def YearPickerInput(key: str | None = None, **props: Any): ...
