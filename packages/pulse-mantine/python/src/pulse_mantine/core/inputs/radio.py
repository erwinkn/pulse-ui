from typing import Optional
import pulse as ps


@ps.react_component("Radio", "@mantine/core")
def Radio(key: Optional[str] = None, **props): ...


# Only Radio component that needs to be registered as a form input
@ps.react_component("RadioGroup", "pulse-mantine")
def RadioGroup(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Radio", "@mantine/core", prop="Card")
def RadioCard(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Radio", "@mantine/core", prop="Indicator")
def RadioIndicator(*children: ps.Child, key: Optional[str] = None, **props): ...
