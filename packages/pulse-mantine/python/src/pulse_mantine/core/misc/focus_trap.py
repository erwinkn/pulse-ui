from typing import Optional
import pulse as ps


@ps.react_component("FocusTrap", "@mantine/core")
def FocusTrap(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("FocusTrap", "@mantine/core", prop="InitialFocus")
def FocusTrapInitialFocus(key: Optional[str] = None, **props): ...

