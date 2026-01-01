from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Rating", "pulse-mantine"))
def Rating(key: str | None = None, **props: Any): ...
