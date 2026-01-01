from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ColorInput", "pulse-mantine"))
def ColorInput(key: str | None = None, **props: Any): ...
