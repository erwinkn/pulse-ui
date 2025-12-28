from typing import Any

import pulse as ps


@ps.react_component(ps.Import("FileButton", "@mantine/core"))
def FileButton(*children: ps.Node, key: str | None = None, **props: Any): ...
