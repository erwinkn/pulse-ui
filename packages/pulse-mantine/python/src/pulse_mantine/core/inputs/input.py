from typing import Optional
import pulse as ps


@ps.react_component("Input", "@mantine/core")
def Input(key: Optional[str] = None, **props): ...


@ps.react_component("Input", "@mantine/core", prop="Label")
def InputLabel(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Input", "@mantine/core", prop="Error")
def InputError(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Input", "@mantine/core", prop="Description")
def InputDescription(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Input", "@mantine/core", prop="Placeholder")
def InputPlaceholder(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Input", "@mantine/core", prop="Wrapper")
def InputWrapper(*children: ps.Child, key: Optional[str] = None, **props): ...


@ps.react_component("Input", "@mantine/core", prop="ClearButton")
def InputClearButton(key: Optional[str] = None, **props): ...

