from typing import Any

import pulse as ps


@ps.react_component(ps.Import("LoadingOverlay", "@mantine/core"))
def LoadingOverlay(key: str | None = None, **props: Any): ...
