from typing import Any

import pulse as ps

_FocusTrap = ps.Import("FocusTrap", "@mantine/core")


@ps.react_component(_FocusTrap)
def FocusTrap(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_FocusTrap.InitialFocus)
def FocusTrapInitialFocus(key: str | None = None, **props: Any): ...
