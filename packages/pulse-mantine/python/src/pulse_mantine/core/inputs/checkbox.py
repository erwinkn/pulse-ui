from typing import Any

import pulse as ps

_Checkbox = ps.Import("Checkbox", "@mantine/core")


@ps.react_component(ps.Import("Checkbox", "pulse-mantine"))
def Checkbox(key: str | None = None, **props: Any): ...


@ps.react_component(_Checkbox.Group)
def CheckboxGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Checkbox.Indicator)
def CheckboxIndicator(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Checkbox.Card)
def CheckboxCard(*children: ps.Node, key: str | None = None, **props: Any): ...
