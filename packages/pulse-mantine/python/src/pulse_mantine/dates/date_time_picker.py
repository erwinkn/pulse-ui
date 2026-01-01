from typing import Any

import pulse as ps


@ps.react_component(ps.Import("DateTimePicker", "pulse-mantine"))
def DateTimePicker(key: str | None = None, **props: Any): ...
