from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Avatar", "@mantine/core"))
def Avatar(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Avatar", "@mantine/core", prop="Group"))
def AvatarGroup(*children: ps.Node, key: str | None = None, **props: Any): ...
