from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Overlay", "@mantine/core"))
def Overlay(key: str | None = None, **props: Any): ...
