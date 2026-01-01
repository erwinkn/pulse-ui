from typing import Any

import pulse as ps

_Card = ps.Import("Card", "@mantine/core")


@ps.react_component(_Card)
def Card(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Card.Section)
def CardSection(*children: ps.Node, key: str | None = None, **props: Any): ...
