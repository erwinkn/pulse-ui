from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ColorSwatch", "@mantine/core"))
def ColorSwatch(*children: ps.Node, key: str | None = None, **props: Any): ...
