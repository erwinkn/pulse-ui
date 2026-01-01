from typing import Any

import pulse as ps


@ps.react_component(ps.Import("TagsInput", "@mantine/core"))
def TagsInput(key: str | None = None, **props: Any): ...
