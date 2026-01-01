from typing import Any

import pulse as ps


@ps.react_component(ps.Import("TimePicker", "pulse-mantine"))
def TimePicker(key: str | None = None, **props: Any): ...
