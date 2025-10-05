from typing import Optional
import pulse as ps


@ps.react_component("Skeleton", "@mantine/core")
def Skeleton(*children: ps.Child, key: Optional[str] = None, **props): ...

