import pulse as ps
from typing import Any


@ps.react_component("Notification", "@mantine/core")
def Notification(*children: ps.Child, key: str | None = None, **props: Any): ...
