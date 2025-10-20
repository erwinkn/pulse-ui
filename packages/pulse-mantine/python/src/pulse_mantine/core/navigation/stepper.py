import pulse as ps
from typing import Any


@ps.react_component("Stepper", "@mantine/core")
def Stepper(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Stepper", "@mantine/core", prop="Step")
def StepperStep(*children: ps.Child, key: str | None = None, **props: Any): ...


@ps.react_component("Stepper", "@mantine/core", prop="Completed")
def StepperCompleted(*children: ps.Child, key: str | None = None, **props: Any): ...
