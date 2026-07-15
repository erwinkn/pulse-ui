from typing import Any

import pulse as ps


@ps.react_component(ps.Import("TagsInput", "pulse-mantine"))
def TagsInput(key: str | None = None, **props: Any): ...
