from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Button", "@mantine/core"))
def Button(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Button", "@mantine/core", prop="Group"))
def ButtonGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Button", "@mantine/core", prop="GroupSection"))
def ButtonGroupSection(*children: ps.Node, key: str | None = None, **props: Any): ...
