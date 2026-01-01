from typing import Any

import pulse as ps


@ps.react_component(ps.Import("NavLink", "@mantine/core"))
def NavLink(*children: ps.Node, key: str | None = None, **props: Any): ...
