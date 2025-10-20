import pulse as ps
from typing import Any


@ps.react_component("Kbd", "@mantine/core")
def Kbd(*children: ps.Child, key: str | None = None, **props: Any): ...
