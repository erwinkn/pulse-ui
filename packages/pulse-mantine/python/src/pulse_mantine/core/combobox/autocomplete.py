from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Autocomplete", "pulse-mantine"))
def Autocomplete(key: str | None = None, **props: Any): ...
