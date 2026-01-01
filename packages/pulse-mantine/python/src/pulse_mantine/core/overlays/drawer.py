from typing import Any

import pulse as ps

_Drawer = ps.Import("Drawer", "@mantine/core")


@ps.react_component(_Drawer)
def Drawer(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Root)
def DrawerRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Overlay)
def DrawerOverlay(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Content)
def DrawerContent(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Body)
def DrawerBody(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Header)
def DrawerHeader(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Title)
def DrawerTitle(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.CloseButton)
def DrawerCloseButton(key: str | None = None, **props: Any): ...


@ps.react_component(_Drawer.Stack)
def DrawerStack(*children: ps.Node, key: str | None = None, **props: Any): ...
