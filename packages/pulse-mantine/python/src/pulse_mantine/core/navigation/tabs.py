from typing import Any

import pulse as ps

_Tabs = ps.Import("Tabs", "@mantine/core")


@ps.react_component(_Tabs)
def Tabs(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Tabs.Tab)
def TabsTab(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Tabs.Panel)
def TabsPanel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Tabs.List)
def TabsList(*children: ps.Node, key: str | None = None, **props: Any): ...
