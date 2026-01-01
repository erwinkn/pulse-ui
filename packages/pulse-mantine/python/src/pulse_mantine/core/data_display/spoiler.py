from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Spoiler", "@mantine/core"))
def Spoiler(*children: ps.Node, key: str | None = None, **props: Any): ...
