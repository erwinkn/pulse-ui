from typing import Any

import pulse as ps


@ps.react_component(ps.Import("YearsList", "pulse-mantine"))
def YearsList(key: str | None = None, **props: Any): ...
