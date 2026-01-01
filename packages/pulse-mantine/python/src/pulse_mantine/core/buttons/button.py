from typing import Any

import pulse as ps

_Button = ps.Import("Button", "@mantine/core")


@ps.react_component(_Button)
def Button(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Button.Group)
def ButtonGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Button.GroupSection)
def ButtonGroupSection(*children: ps.Node, key: str | None = None, **props: Any): ...
