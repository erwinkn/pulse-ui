import pulse as ps
from typing import Any


@ps.react_component("Portal", "@mantine/core")
def Portal(*children: ps.Child, key: str | None = None, **props: Any): ...
