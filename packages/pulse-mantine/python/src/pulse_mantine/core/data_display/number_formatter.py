from typing import Any

import pulse as ps


@ps.react_component(ps.Import("NumberFormatter", "@mantine/core"))
def NumberFormatter(key: str | None = None, **props: Any): ...
