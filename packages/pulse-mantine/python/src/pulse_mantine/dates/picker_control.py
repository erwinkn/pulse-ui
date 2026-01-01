from typing import Any

import pulse as ps


@ps.react_component(ps.Import("PickerControl", "pulse-mantine"))
def PickerControl(*children: ps.Node, key: str | None = None, **props: Any): ...
