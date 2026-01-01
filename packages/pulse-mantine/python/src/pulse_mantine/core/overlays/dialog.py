from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Dialog", "@mantine/core"))
def Dialog(*children: ps.Node, key: str | None = None, **props: Any): ...
