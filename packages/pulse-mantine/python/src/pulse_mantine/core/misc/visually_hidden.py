from typing import Any

import pulse as ps


@ps.react_component(ps.Import("VisuallyHidden", "@mantine/core"))
def VisuallyHidden(*children: ps.Node, key: str | None = None, **props: Any): ...
