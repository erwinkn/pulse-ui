from typing import Any

import pulse as ps


@ps.react_component("Skeleton", "@mantine/core")
def Skeleton(*children: ps.Child, key: str | None = None, **props: Any): ...
