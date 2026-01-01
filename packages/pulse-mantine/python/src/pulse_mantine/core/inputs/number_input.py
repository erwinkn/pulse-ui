from typing import Any

import pulse as ps


@ps.react_component(ps.Import("NumberInput", "pulse-mantine"))
def NumberInput(*children: ps.Node, key: str | None = None, **props: Any): ...
