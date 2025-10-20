from pathlib import Path
import pulse as ps


class ToggleState(ps.State):
    enabled: bool = True

    def __init__(self, label: str):
        self._label = label

    def toggle(self):
        print(f"[toggle] {self._label}")
        self.enabled = not self.enabled

    @ps.effect
    def log_toggle_change(self):
        # Reading self.enabled registers it as a dependency
        print(f"[effect] {self._label}, enabled = {self.enabled}")

        # This will be executed before each subsequent effect execution and upon
        # effect disposal (when the state is not used anymore).
        def cleanup():
            print(f"[cleanup] {self._label}")

        return cleanup


@ps.component
def Toggle(label: str):
    state = ps.states(ToggleState(label))

    return ps.div(className="flex flex-col")[
        ps.div(className="flex items-center gap-2")[
            ps.input(
                id=label, type="checkbox", checked=state.enabled, onChange=state.toggle
            ),
            ps.label(label, htmlFor=label),
            f"Enabled: {state.enabled}",
        ]
    ]


@ps.component
def SetupEffectDemo():
    return ps.div(
        className="w-fit mx-auto h-screen justify-center flex flex-col items-start gap-2"
    )[Toggle("Toggle 1"), Toggle("Toggle 2")]


app = ps.App(
    routes=[ps.Route("/", SetupEffectDemo)],
)
