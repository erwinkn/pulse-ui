from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Pill", "@mantine/core"))
def Pill(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Pill", "@mantine/core", prop="Group"))
def PillGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
