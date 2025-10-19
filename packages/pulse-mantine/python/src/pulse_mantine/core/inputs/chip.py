import pulse as ps


@ps.react_component("Chip", "pulse-mantine")
def Chip(key: str | None = None, **props): ...


@ps.react_component("Chip", "@mantine/core", prop="Group")
def ChipGroup(*children: ps.Child, key: str | None = None, **props): ...
