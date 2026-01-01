from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Text", "@mantine/core"))
def Text(*children: ps.Node, key: str | None = None, **props: Any): ...
