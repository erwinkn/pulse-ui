from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Switch", "pulse-mantine"))
def Switch(key: str | None = None, **props: Any): ...
