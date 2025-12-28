from typing import Any

import pulse as ps


@ps.react_component(ps.Import("PillsInput", "@mantine/core"))
def PillsInput(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("PillsInput", "@mantine/core", prop="Field"))
def PillsInputField(*children: ps.Node, key: str | None = None, **props: Any): ...
