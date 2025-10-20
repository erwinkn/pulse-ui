from typing import Any

import pulse as ps


@ps.react_component("NavLink", "@mantine/core")
def NavLink(*children: ps.Child, key: str | None = None, **props: Any): ...
