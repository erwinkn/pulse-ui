from typing import Any

import pulse as ps

_Modal = ps.Import("Modal", "@mantine/core")


@ps.react_component(_Modal)
def Modal(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Root)
def ModalRoot(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Overlay)
def ModalOverlay(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Content)
def ModalContent(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Body)
def ModalBody(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Header)
def ModalHeader(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Title)
def ModalTitle(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.CloseButton)
def ModalCloseButton(key: str | None = None, **props: Any): ...


@ps.react_component(_Modal.Stack)
def ModalStack(*children: ps.Node, key: str | None = None, **props: Any): ...
