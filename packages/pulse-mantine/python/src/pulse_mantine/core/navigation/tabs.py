from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Tabs", "@mantine/core"))
def Tabs(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Tabs", "@mantine/core", prop="Tab"))
def TabsTab(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Tabs", "@mantine/core", prop="Panel"))
def TabsPanel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Tabs", "@mantine/core", prop="List"))
def TabsList(*children: ps.Node, key: str | None = None, **props: Any): ...
