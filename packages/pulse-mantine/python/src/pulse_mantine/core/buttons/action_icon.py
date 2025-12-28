from typing import Any

import pulse as ps


@ps.react_component(ps.Import("ActionIcon", "@mantine/core"))
def ActionIcon(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("ActionIcon", "@mantine/core", prop="Group"))
def ActionIconGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("ActionIcon", "@mantine/core", prop="GroupSection"))
def ActionIconGroupSection(
	*children: ps.Node, key: str | None = None, **props: Any
): ...
