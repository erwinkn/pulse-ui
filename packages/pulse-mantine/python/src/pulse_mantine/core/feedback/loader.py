from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Loader", "@mantine/core"))
def Loader(*children: ps.Node, key: str | None = None, **props: Any): ...
