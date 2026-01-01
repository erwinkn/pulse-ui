from typing import Any

import pulse as ps


@ps.react_component(ps.Import("HiddenDatesInput", "pulse-mantine"))
def HiddenDatesInput(key: str | None = None, **props: Any): ...
