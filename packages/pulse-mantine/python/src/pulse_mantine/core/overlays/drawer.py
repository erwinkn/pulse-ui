from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Drawer", "@mantine/core"))
def Drawer(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Root"))
def DrawerRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Overlay"))
def DrawerOverlay(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Content"))
def DrawerContent(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Body"))
def DrawerBody(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Header"))
def DrawerHeader(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Title"))
def DrawerTitle(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="CloseButton"))
def DrawerCloseButton(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Drawer", "@mantine/core", prop="Stack"))
def DrawerStack(*children: ps.Node, key: str | None = None, **props: Any): ...
