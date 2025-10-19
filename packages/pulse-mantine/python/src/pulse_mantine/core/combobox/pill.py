import pulse as ps


@ps.react_component("Pill", "@mantine/core")
def Pill(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Pill", "@mantine/core", prop="Group")
def PillGroup(*children: ps.Child, key: str | None = None, **props): ...
