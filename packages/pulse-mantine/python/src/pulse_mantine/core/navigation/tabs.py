import pulse as ps
from typing import Any


@ps.react_component("Tabs", "@mantine/core")
def Tabs(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Tabs", "@mantine/core", prop="Tab")
def TabsTab(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Tabs", "@mantine/core", prop="Panel")
def TabsPanel(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Tabs", "@mantine/core", prop="List")
def TabsList(*children: ps.Child, key: str | None = None, **props: Any): ...
