from typing import Any

import pulse as ps


@ps.react_component(ps.Import("BackgroundImage", "@mantine/core"))
def BackgroundImage(*children: ps.Node, key: str | None = None, **props: Any): ...
