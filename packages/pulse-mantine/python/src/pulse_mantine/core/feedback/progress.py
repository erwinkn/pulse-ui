from typing import Any

import pulse as ps

_Progress = ps.Import("Progress", "@mantine/core")


@ps.react_component(_Progress)
def Progress(key: str | None = None, **props: Any): ...


@ps.react_component(_Progress.Section)
def ProgressSection(key: str | None = None, **props: Any): ...


@ps.react_component(_Progress.Root)
def ProgressRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Progress.Label)
def ProgressLabel(*children: ps.Node, key: str | None = None, **props: Any): ...
