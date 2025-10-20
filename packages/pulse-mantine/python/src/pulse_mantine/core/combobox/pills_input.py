from typing import Any

import pulse as ps


@ps.react_component("PillsInput", "@mantine/core")
def PillsInput(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("PillsInput", "@mantine/core", prop="Field")
def PillsInputField(*children: ps.Child, key: str | None = None, **props: Any): ...
