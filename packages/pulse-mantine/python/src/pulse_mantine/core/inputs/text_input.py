from typing import Any

import pulse as ps


@ps.react_component(ps.Import("TextInput", "pulse-mantine"))
def TextInput(*children: ps.Node, key: str | None = None, **props: Any): ...
