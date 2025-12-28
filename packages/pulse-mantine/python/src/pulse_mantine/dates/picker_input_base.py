from typing import Any

import pulse as ps


@ps.react_component(ps.Import("PickerInputBase", "pulse-mantine"))
def PickerInputBase(key: str | None = None, **props: Any): ...
