from typing import Any

import pulse as ps


@ps.react_component("Badge", "@mantine/core")
def Badge(*children: ps.Child, key: str | None = None, **props: Any): ...
