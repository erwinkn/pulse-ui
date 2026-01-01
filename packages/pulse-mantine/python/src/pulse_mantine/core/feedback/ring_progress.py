from typing import Any

import pulse as ps


@ps.react_component(ps.Import("RingProgress", "@mantine/core"))
def RingProgress(key: str | None = None, **props: Any): ...
