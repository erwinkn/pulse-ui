from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Fieldset", "@mantine/core"))
def Fieldset(*children: ps.Node, key: str | None = None, **props: Any): ...
