import pulse as ps
from typing import Any


@ps.react_component("Skeleton", "@mantine/core")
def Skeleton(*children: ps.Child, key: str | None = None, **props: Any): ...
