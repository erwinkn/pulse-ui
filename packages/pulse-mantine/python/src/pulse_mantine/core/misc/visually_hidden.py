import pulse as ps
from typing import Any


@ps.react_component("VisuallyHidden", "@mantine/core")
def VisuallyHidden(*children: ps.Child, key: str | None = None, **props: Any): ...
