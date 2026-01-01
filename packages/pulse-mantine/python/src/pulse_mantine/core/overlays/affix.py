from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Affix", "@mantine/core"))
def Affix(*children: ps.Node, key: str | None = None, **props: Any): ...
