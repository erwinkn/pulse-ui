from typing import Any

import pulse as ps


@ps.react_component("Progress", "@mantine/core")
def Progress(key: str | None = None, **props: Any): ...


@ps.react_component("Progress", "@mantine/core", prop="Section")
def ProgressSection(key: str | None = None, **props: Any): ...


@ps.react_component("Progress", "@mantine/core", prop="Root")
def ProgressRoot(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Progress", "@mantine/core", prop="Label")
def ProgressLabel(*children: ps.Child, key: str | None = None, **props: Any): ...
