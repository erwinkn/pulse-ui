from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Badge", "@mantine/core"))
def Badge(*children: ps.Node, key: str | None = None, **props: Any): ...
