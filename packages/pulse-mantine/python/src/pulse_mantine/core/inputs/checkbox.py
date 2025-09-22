from typing import Optional
import pulse as ps


@ps.react_component("Checkbox", "@mantine/core")
def Checkbox(key: Optional[str] = None, **props): ...


@ps.react_component("Checkbox", "@mantine/core", prop="Group")
def CheckboxGroup(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Checkbox", "@mantine/core", prop="Indicator")
def CheckboxIndicator(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Checkbox", "@mantine/core", prop="Card")
def CheckboxCard(*children: ps.Child, key: Optional[str] = None, **props): ...