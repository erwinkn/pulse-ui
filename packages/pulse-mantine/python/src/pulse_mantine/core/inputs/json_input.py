from typing import Any

import pulse as ps


@ps.react_component(ps.Import("JsonInput", "pulse-mantine"))
def JsonInput(key: str | None = None, **props: Any): ...
