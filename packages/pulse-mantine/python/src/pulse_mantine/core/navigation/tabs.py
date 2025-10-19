import pulse as ps


@ps.react_component("Tabs", "@mantine/core")
def Tabs(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Tabs", "@mantine/core", prop="Tab")
def TabsTab(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Tabs", "@mantine/core", prop="Panel")
def TabsPanel(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Tabs", "@mantine/core", prop="List")
def TabsList(*children: ps.Child, key: str | None = None, **props): ...
