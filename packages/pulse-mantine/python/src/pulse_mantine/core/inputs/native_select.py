from typing import Any

import pulse as ps


@ps.react_component(ps.Import("NativeSelect", "pulse-mantine"))
def NativeSelect(*children: ps.Node, key: str | None = None, **props: Any): ...
