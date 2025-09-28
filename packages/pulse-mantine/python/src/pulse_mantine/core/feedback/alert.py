from typing import Optional
import pulse as ps


@ps.react_component("Alert", "@mantine/core")
def Alert(*children: ps.Child, key: Optional[str] = None, **props): ...

