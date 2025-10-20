import pulse as ps
from typing import Any


@ps.react_component("Checkbox", "pulse-mantine")
def Checkbox(key: str | None = None, **props: Any): ...


@ps.react_component("Checkbox", "@mantine/core", prop="Group")
def CheckboxGroup(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Checkbox", "@mantine/core", prop="Indicator")
def CheckboxIndicator(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Checkbox", "@mantine/core", prop="Card")
def CheckboxCard(*children: ps.Child, key: str | None = None, **props: Any): ...
