import pulse as ps
from typing import Any


@ps.react_component("Pill", "@mantine/core")
def Pill(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Pill", "@mantine/core", prop="Group")
def PillGroup(*children: ps.Child, key: str | None = None, **props: Any): ...
