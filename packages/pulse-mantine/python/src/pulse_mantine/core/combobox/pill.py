from typing import Any

import pulse as ps

_Pill = ps.Import("Pill", "@mantine/core")


@ps.react_component(_Pill)
def Pill(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Pill.Group)
def PillGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
