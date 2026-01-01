from typing import Any

import pulse as ps


@ps.react_component(ps.Import("CopyButton", "@mantine/core"))
def CopyButton(*children: ps.Node, key: str | None = None, **props: Any): ...
