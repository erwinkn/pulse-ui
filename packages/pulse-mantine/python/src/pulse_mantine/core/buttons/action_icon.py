import pulse as ps
from typing import Any


@ps.react_component("ActionIcon", "@mantine/core")
def ActionIcon(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("ActionIcon", "@mantine/core", prop="Group")
def ActionIconGroup(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("ActionIcon", "@mantine/core", prop="GroupSection")
def ActionIconGroupSection(*children: ps.Child, key: str | None = None, **props: Any): ...
