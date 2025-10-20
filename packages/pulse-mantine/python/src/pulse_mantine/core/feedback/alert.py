import pulse as ps
from typing import Any


@ps.react_component("Alert", "@mantine/core")
def Alert(*children: ps.Child, key: str | None = None, **props: Any): ...
