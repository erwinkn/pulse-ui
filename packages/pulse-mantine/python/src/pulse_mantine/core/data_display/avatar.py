from typing import Any

import pulse as ps


@ps.react_component("Avatar", "@mantine/core")
def Avatar(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Avatar", "@mantine/core", prop="Group")
def AvatarGroup(*children: ps.Child, key: str | None = None, **props: Any): ...
