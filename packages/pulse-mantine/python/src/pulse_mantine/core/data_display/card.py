from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Card", "@mantine/core"))
def Card(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Card", "@mantine/core", prop="Section"))
def CardSection(*children: ps.Node, key: str | None = None, **props: Any): ...
