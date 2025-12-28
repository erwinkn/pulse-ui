from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Calendar", "pulse-mantine"))
def Calendar(key: str | None = None, **props: Any): ...
