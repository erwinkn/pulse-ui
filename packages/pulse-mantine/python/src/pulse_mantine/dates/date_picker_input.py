from typing import Any

import pulse as ps


@ps.react_component(ps.Import("DatePickerInput", "pulse-mantine"))
def DatePickerInput(key: str | None = None, **props: Any): ...
