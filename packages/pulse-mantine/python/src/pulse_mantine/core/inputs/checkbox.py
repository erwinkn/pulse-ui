from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Checkbox", "pulse-mantine"))
def Checkbox(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Checkbox", "@mantine/core", prop="Group"))
def CheckboxGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Checkbox", "@mantine/core", prop="Indicator"))
def CheckboxIndicator(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Checkbox", "@mantine/core", prop="Card"))
def CheckboxCard(*children: ps.Node, key: str | None = None, **props: Any): ...
