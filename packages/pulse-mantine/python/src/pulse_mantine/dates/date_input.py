from typing import Any

import pulse as ps


@ps.react_component(ps.Import("DateInput", "pulse-mantine"))
def DateInput(key: str | None = None, **props: Any): ...
