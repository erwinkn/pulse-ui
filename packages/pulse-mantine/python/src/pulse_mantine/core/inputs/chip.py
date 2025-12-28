from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Chip", "pulse-mantine"))
def Chip(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Chip", "@mantine/core", prop="Group"))
def ChipGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
