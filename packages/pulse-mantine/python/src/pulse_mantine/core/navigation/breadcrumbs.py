from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Breadcrumbs", "@mantine/core"))
def Breadcrumbs(*children: ps.Node, key: str | None = None, **props: Any): ...
