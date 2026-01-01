from typing import Any

import pulse as ps


@ps.react_component(ps.Import("DatePicker", "pulse-mantine"))
def DatePicker(key: str | None = None, **props: Any): ...
