from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ColorPicker", "pulse-mantine"))
def ColorPicker(key: str | None = None, **props: Any): ...
