from typing import Optional
import pulse as ps


@ps.react_component("Progress", "@mantine/core")
def Progress(key: Optional[str] = None, **props): ...


@ps.react_component("Progress", "@mantine/core", prop="Section")
def ProgressSection(key: Optional[str] = None, **props): ...


@ps.react_component("Progress", "@mantine/core", prop="Root")
def ProgressRoot(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Progress", "@mantine/core", prop="Label")
def ProgressLabel(*children: ps.Child, key: Optional[str] = None, **props): ...

