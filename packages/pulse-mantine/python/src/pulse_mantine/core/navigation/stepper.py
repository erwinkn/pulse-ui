from typing import Any

import pulse as ps

_Stepper = ps.Import("Stepper", "@mantine/core")


@ps.react_component(_Stepper)
def Stepper(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Stepper.Step)
def StepperStep(*children: ps.Node, key: str | None = None, **props: Any): ...


@ps.react_component(_Stepper.Completed)
def StepperCompleted(*children: ps.Node, key: str | None = None, **props: Any): ...
