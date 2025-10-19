import pulse as ps


@ps.react_component("Button", "@mantine/core")
def Button(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Button", "@mantine/core", prop="Group")
def ButtonGroup(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Button", "@mantine/core", prop="GroupSection")
def ButtonGroupSection(*children: ps.Child, key: str | None = None, **props): ...
