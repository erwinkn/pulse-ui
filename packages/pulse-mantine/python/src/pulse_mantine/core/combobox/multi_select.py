from typing import Any

import pulse as ps


@ps.react_component(ps.Import("MultiSelect", "pulse-mantine"))
def MultiSelect(key: str | None = None, **props: Any): ...
