import pulse as ps
from typing import Any


@ps.react_component("Loader", "@mantine/core")
def Loader(*children: ps.Child, key: str | None = None, **props: Any): ...
