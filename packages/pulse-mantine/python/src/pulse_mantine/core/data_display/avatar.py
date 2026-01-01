from typing import Any

import pulse as ps

_Avatar = ps.Import("Avatar", "@mantine/core")


@ps.react_component(_Avatar)
def Avatar(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Avatar.Group)
def AvatarGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
