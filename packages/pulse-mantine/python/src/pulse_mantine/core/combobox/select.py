from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Select", "pulse-mantine"))
def Select(key: str | None = None, **props: Any): ...
