from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Image", "@mantine/core"))
def Image(key: str | None = None, **props: Any): ...
