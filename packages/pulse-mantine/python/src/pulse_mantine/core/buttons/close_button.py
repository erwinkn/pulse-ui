from typing import Any

import pulse as ps


@ps.react_component(ps.Import("CloseButton", "@mantine/core"))
def CloseButton(key: str | None = None, **props: Any): ...
