from typing import Any

import pulse as ps


@ps.react_component(ps.Import("TimeValue", "pulse-mantine"))
def TimeValue(key: str | None = None, **props: Any): ...
