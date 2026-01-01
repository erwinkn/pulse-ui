from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Paper", "@mantine/core"))
def Paper(*children: ps.Node, key: str | None = None, **props: Any): ...
