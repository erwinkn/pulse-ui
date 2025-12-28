from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Progress", "@mantine/core"))
def Progress(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Progress", "@mantine/core", prop="Section"))
def ProgressSection(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Progress", "@mantine/core", prop="Root"))
def ProgressRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Progress", "@mantine/core", prop="Label"))
def ProgressLabel(*children: ps.Node, key: str | None = None, **props: Any): ...
