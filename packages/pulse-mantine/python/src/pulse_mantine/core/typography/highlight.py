from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Highlight", "@mantine/core"))
def Highlight(key: str | None = None, **props: Any): ...
