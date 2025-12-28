from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Portal", "@mantine/core"))
def Portal(*children: ps.Node, key: str | None = None, **props: Any): ...
