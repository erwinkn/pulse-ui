from typing import Any

import pulse as ps


@ps.react_component(ps.Import("MultiSelect", "@mantine/core"))
def MultiSelect(key: str | None = None, **props: Any): ...
