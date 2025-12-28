from typing import Any

import pulse as ps


@ps.react_component(ps.Import("MonthsList", "pulse-mantine"))
def MonthsList(key: str | None = None, **props: Any): ...
