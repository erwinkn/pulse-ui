import asyncio
from typing import Any

import pulse as ps
from pulse_mantine import (
    Button,
    Group,
    HasLength,
    IsEmail,
    IsNotEmpty,
    MantineForm,
    Matches,
    ServerValidation,
    TextInput,
)


class UsernameForm(MantineForm):
    def __init__(self) -> None:
        validate = {
            "username": [
                # Client-side validators (run on change)
                IsNotEmpty("Username is required"),
                HasLength(min=3, max=16, error="3-16 characters"),
                Matches(
                    r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"
                ),
                # Async server validator runs on blur only
                ServerValidation(
                    self.username_available, debounce_ms=150, run_on="blur"
                ),
            ],
            "email": [IsEmail("Enter a valid email")],
        }

        super().__init__(
            initialValues={"username": "", "email": ""},
            validate=validate,
            mode="controlled",
            # Run client-side validators on change for instant feedback
            validateInputOnChange=True,
            clearInputErrorOnChange=True,
            debounceMs=200,
        )

    async def username_available(
        self, value: str, values: dict[str, Any], path: str
    ) -> str | None:  # noqa: ARG001
        # Simulate I/O latency (e.g., database lookup)

        await asyncio.sleep(0.15)
        if not isinstance(value, str):
            return None
        taken = {"admin", "root", "system"}
        return "This username is reserved" if value.strip().lower() in taken else None


@ps.component
def ServerValidationDemo():
    form = ps.states(UsernameForm)

    return form.render(onSubmit=lambda values: print("Submitted:", values))[
        TextInput(
            name="username",
            label="Username",
            placeholder="lowercase letters",
            withAsterisk=True,
        ),
        TextInput(
            name="email",
            label="Email",
            placeholder="you@example.com",
            withAsterisk=True,
        ),
        Group(justify="flex-end", mt="md")[
            Button("Validate now", variant="light", onClick=form.validate),
            Button("Submit", type="submit"),
        ],
    ]


app = ps.App([ps.Route("/", ServerValidationDemo)])
