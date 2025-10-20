from typing import Any

import pulse as ps


@ps.react_component("Fieldset", "@mantine/core")
def Fieldset(*children: ps.Child, key: str | None = None, **props: Any): ...
