from typing import Any

import pulse as ps

_ActionIcon = ps.Import("ActionIcon", "@mantine/core")


@ps.react_component(_ActionIcon)
def ActionIcon(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_ActionIcon.Group)
def ActionIconGroup(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_ActionIcon.GroupSection)
def ActionIconGroupSection(
	*children: ps.Node, key: str | None = None, **props: Any
): ...
