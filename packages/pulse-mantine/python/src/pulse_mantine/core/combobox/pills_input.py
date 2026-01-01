from typing import Any

import pulse as ps

_PillsInput = ps.Import("PillsInput", "@mantine/core")


@ps.react_component(_PillsInput)
def PillsInput(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_PillsInput.Field)
def PillsInputField(*children: ps.Node, key: str | None = None, **props: Any): ...
