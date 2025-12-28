from typing import Any

import pulse as ps


@ps.react_component(ps.Import("UnstyledButton", "@mantine/core"))
def UnstyledButton(*children: ps.Node, key: str | None = None, **props: Any): ...
