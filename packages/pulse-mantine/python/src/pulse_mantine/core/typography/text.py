import pulse as ps
from typing import Any


@ps.react_component("Text", "@mantine/core")
def Text(*children: ps.Child, key: str | None = None, **props: Any): ...
