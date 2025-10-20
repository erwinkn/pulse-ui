import pulse as ps
from typing import Any


@ps.react_component("Transition", "@mantine/core")
def Transition(*children: ps.Child, key: str | None = None, **props: Any): ...
