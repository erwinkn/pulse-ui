from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Textarea", "pulse-mantine"))
def Textarea(*children: ps.Node, key: str | None = None, **props: Any): ...
