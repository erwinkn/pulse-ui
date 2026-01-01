from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Code", "@mantine/core"))
def Code(*children: ps.Node, key: str | None = None, **props: Any): ...
