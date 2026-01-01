from typing import Any

import pulse as ps

_Input = ps.Import("Input", "@mantine/core")


@ps.react_component(_Input)
def Input(key: str | None = None, **props: Any): ...


@ps.react_component(_Input.Label)
def InputLabel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Input.Error)
def InputError(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Input.Description)
def InputDescription(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Input.Placeholder)
def InputPlaceholder(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Input.Wrapper)
def InputWrapper(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Input.ClearButton)
def InputClearButton(key: str | None = None, **props: Any): ...
