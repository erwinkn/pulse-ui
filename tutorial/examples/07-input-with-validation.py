"examples/06-input-with-validation.py"

from pathlib import Path
import pulse as ps


class ValidatedInputState(ps.State):
    value: str = ""
    submitted: bool = False
    error: str | None = None

    def __init__(self, validate, onValid):
        self._validate = validate
        self._onValid = onValid

    def on_change(self, value: str):
        self.value = value
        # Validate on each change after the first submission
        if self.submitted:
            self.error = self._validate(self.value)

    def on_submit(self):
        self.submitted = True
        self.error = self._validate(self.value)
        if not self.error:
            self._onValid(self.value)


@ps.component
def ValidatedInput(label: str, validate, onValid):
    # Warning: the state will not update if `validate` or `onValid` change here!
    state = ps.states(ValidatedInputState(validate, onValid))

    return ps.div(
        ps.label(label, className="block mb-1"),
        ps.input(
            type="text",
            value=state.value,
            onChange=lambda e: state.on_change(e["target"]["value"]),
            className=(
                "border p-2 w-full "
                + ("border-red-500" if state.error else "border-gray-300")
            ),
        ),
        ps.div(
            ps.button(
                "Submit",
                onClick=state.on_submit,
                className="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded mt-2",
            ),
            className="mt-1",
        ),
        ps.small(state.error, className="text-red-600 mt-1 block")
        if state.error
        else None,
    )


# Demo usage
class DemoState(ps.State):
    last_accepted: str = ""

    def on_valid(self, value: str):
        self.last_accepted = value


def validate_email(s: str) -> str | None:
    return (
        None if ("@" in s and "." in s.split("@")[-1]) else "Please enter a valid email"
    )


@ps.component
def ValidatedInputDemo():
    state = ps.states(DemoState)
    return ps.div(className="max-w-xl mx-auto mt-8")[
        ValidatedInput(
            label="Email",
            validate=validate_email,
            onValid=state.on_valid
        ),
        ps.div(
            f"Accepted: {state.last_accepted}"
            if state.last_accepted
            else "No value accepted yet.",
            className="mt-3 text-sm text-gray-600",
        ),
    ]


app = ps.App(
    routes=[ps.Route("/", ValidatedInputDemo)],
)
