from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Autocomplete", "@mantine/core"))
def Autocomplete(key: str | None = None, **props: Any): ...
