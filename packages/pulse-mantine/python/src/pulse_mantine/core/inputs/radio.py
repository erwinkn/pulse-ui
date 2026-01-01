from typing import Any

import pulse as ps

_Radio = ps.Import("Radio", "@mantine/core")


@ps.react_component(_Radio)
def Radio(key: str | None = None, **props: Any): ...


# Only Radio component that needs to be registered as a form input
@ps.react_component(ps.Import("RadioGroup", "pulse-mantine"))
def RadioGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Radio.Card)
def RadioCard(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Radio.Indicator)
def RadioIndicator(*children: ps.Node, key: str | None = None, **props: Any): ...
