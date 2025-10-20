import pulse as ps
from typing import Any


@ps.react_component("Dialog", "@mantine/core")
def Dialog(*children: ps.Child, key: str | None = None, **props: Any): ...
