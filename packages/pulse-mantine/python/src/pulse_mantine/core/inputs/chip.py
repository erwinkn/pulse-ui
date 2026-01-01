from typing import Any

import pulse as ps

_Chip = ps.Import("Chip", "@mantine/core")


@ps.react_component(ps.Import("Chip", "pulse-mantine"))
def Chip(key: str | None = None, **props: Any): ...


@ps.react_component(_Chip.Group)
def ChipGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
