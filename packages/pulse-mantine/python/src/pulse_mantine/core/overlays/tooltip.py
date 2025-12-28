from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Tooltip", "@mantine/core"))
def Tooltip(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Tooltip", "@mantine/core", prop="Floating"))
def TooltipFloating(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Tooltip", "@mantine/core", prop="Group"))
def TooltipGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
