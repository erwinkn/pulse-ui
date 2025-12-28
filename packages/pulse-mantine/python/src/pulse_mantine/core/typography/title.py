from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Title", "@mantine/core"))
def Title(*children: ps.Node, key: str | None = None, **props: Any): ...
