from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Modal", "@mantine/core"))
def Modal(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Root"))
def ModalRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Overlay"))
def ModalOverlay(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Content"))
def ModalContent(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Body"))
def ModalBody(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Header"))
def ModalHeader(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Title"))
def ModalTitle(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="CloseButton"))
def ModalCloseButton(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Modal", "@mantine/core", prop="Stack"))
def ModalStack(*children: ps.Node, key: str | None = None, **props: Any): ...
