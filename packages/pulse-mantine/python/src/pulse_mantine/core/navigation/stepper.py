import pulse as ps


@ps.react_component("Stepper", "@mantine/core")
def Stepper(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Stepper", "@mantine/core", prop="Step")
def StepperStep(*children: ps.Child, key: str | None = None, **props): ...


@ps.react_component("Stepper", "@mantine/core", prop="Completed")
def StepperCompleted(*children: ps.Child, key: str | None = None, **props): ...
