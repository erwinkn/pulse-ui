from typing import Any

import pulse as ps


@ps.react_component(ps.Import("FocusTrap", "@mantine/core"))
def FocusTrap(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("FocusTrap", "@mantine/core", prop="InitialFocus"))
def FocusTrapInitialFocus(key: str | None = None, **props: Any): ...
