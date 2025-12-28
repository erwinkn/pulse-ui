from typing import Any

import pulse as ps


@ps.react_component(ps.Import("Stepper", "@mantine/core"))
def Stepper(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Stepper", "@mantine/core", prop="Step"))
def StepperStep(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(ps.Import("Stepper", "@mantine/core", prop="Completed"))
def StepperCompleted(*children: ps.Node, key: str | None = None, **props: Any): ...
