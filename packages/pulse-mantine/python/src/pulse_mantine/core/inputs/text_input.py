from typing import Optional
import pulse as ps


@ps.react_component("TextInput", "@mantine/core")
def TextInput(*children: ps.Child, key: Optional[str] = None, **props): ...
