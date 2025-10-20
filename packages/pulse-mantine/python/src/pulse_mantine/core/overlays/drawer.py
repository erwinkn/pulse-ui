from typing import Any

import pulse as ps


@ps.react_component("Drawer", "@mantine/core")
def Drawer(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Root")
def DrawerRoot(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Overlay")
def DrawerOverlay(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Content")
def DrawerContent(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Body")
def DrawerBody(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Header")
def DrawerHeader(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Title")
def DrawerTitle(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="CloseButton")
def DrawerCloseButton(key: str | None = None, **props: Any): ...


@ps.react_component("Drawer", "@mantine/core", prop="Stack")
def DrawerStack(*children: ps.Child, key: str | None = None, **props: Any): ...
