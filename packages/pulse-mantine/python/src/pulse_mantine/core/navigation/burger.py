from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Burger", "@mantine/core"))
def Burger(key: str | None = None, **props: Any): ...
