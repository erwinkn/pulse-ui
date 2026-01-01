from typing import Any

import pulse as ps


@ps.react_component(ps.Import("PasswordInput", "pulse-mantine"))
def PasswordInput(key: str | None = None, **props: Any): ...
