from typing import Optional
import pulse as ps


@ps.react_component("Chip", "pulse-mantine")
def Chip(key: Optional[str] = None, **props): ...


@ps.react_component("Chip", "@mantine/core", prop="Group")
def ChipGroup(*children: ps.Child, key: Optional[str] = None, **props): ...
