import pulse as ps
from typing import Any


@ps.react_component("Input", "@mantine/core")
def Input(key: str | None = None, **props: Any): ...


@ps.react_component("Input", "@mantine/core", prop="Label")
def InputLabel(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Input", "@mantine/core", prop="Error")
def InputError(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Input", "@mantine/core", prop="Description")
def InputDescription(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Input", "@mantine/core", prop="Placeholder")
def InputPlaceholder(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Input", "@mantine/core", prop="Wrapper")
def InputWrapper(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Input", "@mantine/core", prop="ClearButton")
def InputClearButton(key: str | None = None, **props: Any): ...
