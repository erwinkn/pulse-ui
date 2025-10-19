import pulse as ps


@ps.react_component("Modal", "@mantine/core")
def Modal(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Root")
def ModalRoot(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Overlay")
def ModalOverlay(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Content")
def ModalContent(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Body")
def ModalBody(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Header")
def ModalHeader(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Title")
def ModalTitle(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="CloseButton")
def ModalCloseButton(key: str | None = None, **props): ...


@ps.react_component("Modal", "@mantine/core", prop="Stack")
def ModalStack(*children: ps.Child, key: str | None = None, **props): ...
