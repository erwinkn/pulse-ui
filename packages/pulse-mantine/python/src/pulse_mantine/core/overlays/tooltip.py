from typing import Any

import pulse as ps

_Tooltip = ps.Import("Tooltip", "@mantine/core")


@ps.react_component(_Tooltip)
def Tooltip(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Tooltip.Floating)
def TooltipFloating(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Tooltip.Group)
def TooltipGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
