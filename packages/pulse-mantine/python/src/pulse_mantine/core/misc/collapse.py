import pulse as ps
from typing import Any


@ps.react_component("Collapse", "@mantine/core")
def Collapse(*children: ps.Child, key: str | None = None, **props: Any): ...
