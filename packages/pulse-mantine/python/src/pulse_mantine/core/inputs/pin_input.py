from typing import Any

import pulse as ps


@ps.react_component(ps.Import("PinInput", "pulse-mantine"))
def PinInput(key: str | None = None, **props: Any): ...
