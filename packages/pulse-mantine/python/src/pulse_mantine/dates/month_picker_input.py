from typing import Any

import pulse as ps


@ps.react_component(ps.Import("MonthPickerInput", "pulse-mantine"))
def MonthPickerInput(key: str | None = None, **props: Any): ...
