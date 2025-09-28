from typing import Optional
import pulse as ps


@ps.react_component("Card", "@mantine/core")
def Card(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Card", "@mantine/core", prop="Section")
def CardSection(*children: ps.Child, key: Optional[str] = None, **props): ...

