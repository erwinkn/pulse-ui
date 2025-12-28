from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Alert", "@mantine/core"))
def Alert(*children: ps.Node, key: str | None = None, **props: Any): ...
