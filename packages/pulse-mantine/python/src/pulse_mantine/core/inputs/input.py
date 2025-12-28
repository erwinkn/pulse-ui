from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Input", "@mantine/core"))
def Input(key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Input", "@mantine/core", prop="Label"))
def InputLabel(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Input", "@mantine/core", prop="Error"))
def InputError(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Input", "@mantine/core", prop="Description"))
def InputDescription(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Input", "@mantine/core", prop="Placeholder"))
def InputPlaceholder(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Input", "@mantine/core", prop="Wrapper"))
def InputWrapper(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Input", "@mantine/core", prop="ClearButton"))
def InputClearButton(key: str | None = None, **props: Any): ...
