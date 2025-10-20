import pulse as ps
from typing import Any


@ps.react_component("Card", "@mantine/core")
def Card(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Card", "@mantine/core", prop="Section")
def CardSection(*children: ps.Child, key: str | None = None, **props: Any): ...
