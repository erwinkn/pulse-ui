from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Blockquote", "@mantine/core"))
def Blockquote(*children: ps.Node, key: str | None = None, **props: Any): ...
