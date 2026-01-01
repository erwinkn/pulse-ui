from typing import Any

import pulse as ps


@ps.react_component(ps.Import("FileInput", "pulse-mantine"))
def FileInput(*children: ps.Node, key: str | None = None, **props: Any): ...
