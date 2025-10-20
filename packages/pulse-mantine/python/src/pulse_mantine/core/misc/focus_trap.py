from typing import Any

import pulse as ps


@ps.react_component("FocusTrap", "@mantine/core")
def FocusTrap(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("FocusTrap", "@mantine/core", prop="InitialFocus")
def FocusTrapInitialFocus(key: str | None = None, **props: Any): ...
