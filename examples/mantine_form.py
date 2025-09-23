from pathlib import Path  # noqa: F401
import pulse as ps
from pulse_mantine import (
    MantineProvider,
    Group,
    Stack,
    Card,
    Button,
    Title,
    Text,
    SegmentedControl,
    Divider,
    TextInput,
    PasswordInput,
    Checkbox,
    Select,
)
from pulse_mantine import Form
from pulse_mantine.form import (
    FormMode,
    Validation,
    IsEmail,
    IsNotEmpty,
    HasLength,
    Matches,
    MatchesField,
    IsInRange,
    IsJSONString,
    IsNotEmptyHTML,
    ServerValidation,
)


class FormDemoState(ps.State):
    mode = "change"  # 'submit' | 'blur' | 'change'
    debounce: int = 300
    addresses_len: int = 1

    def __init__(self):
        self._form = Form()

    @property
    def Form(self):
        return self._form.Component

    def set_mode(self, mode: str):
        self.mode = mode

    def set_debounce(self, val: int):
        self.debounce = val

    def add_address(self):
        self.addresses_len += 1
        self._form.insert_list_item("addresses", {"street": "", "city": ""})

    def remove_address(self, idx: int):
        print(f"Removing address {idx}")
        if self.addresses_len > 1:
            self.addresses_len -= 1
            self._form.remove_list_item("addresses", idx)

    def remove_last(self):
        self.remove_address(self.addresses_len - 1)

    def simulate_errors(self):
        # Demonstrate server-driven errors mapping to Mantine form
        self._form.set_field_error("email", "Please enter a valid email address")
        self._form.set_field_error("password", "Password must be at least 8 characters")


@ps.component
def ValidationModeToggle(st: FormDemoState):
    return Stack(gap="xs")[
        Title("Validation Mode", order=5),
        SegmentedControl(
            data=[
                {"label": "Submit", "value": "submit"},
                {"label": "Blur", "value": "blur"},
                {"label": "Change", "value": "change"},
            ],
            value=st.mode,
            onChange=lambda v: st.set_mode(v),
        ),
        Group(gap="sm")[
            Text(f"Current: {st.mode}"),
            SegmentedControl(
                data=[
                    {"label": "100ms", "value": "100"},
                    {"label": "300ms", "value": "300"},
                    {"label": "1000ms", "value": "1000"},
                ],
                value=str(st.debounce),
                onChange=lambda v: st.set_debounce(int(v)),
            ),
            Text("(server debounce for onChange)"),
        ],
    ]


@ps.component
def ComplexFormDemo():
    st = ps.states(FormDemoState)

    # Initial values include nested list
    initial_values = {
        "username": "",
        "email": "",
        "password": "",
        "confirm": "",
        "newsletter": False,
        "role": "user",
        "addresses": [{"street": "", "city": ""}],
    }

    def username_server(value: str, values: dict, path: str):
        # Simulate uniqueness check
        taken = {"admin", "root", "erwin"}
        if value in taken:
            return "Username is taken"

    def email_server(value: str, values: dict, path: str):
        # Require company domain to verify string return sets error
        if isinstance(value, str) and value and not value.endswith("@acme.io"):
            return "Please use your @acme.io email"
        return None

    validate: Validation = {
        # Username: regex + length + server(unique) with per-field debounce override
        "username": [
            Matches(r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"),
            HasLength(min=3, max=16, error="3-16 chars"),
            ServerValidation(username_server, debounce_ms=st.debounce),
        ],
        # Email: client + server(domain)
        "email": [IsEmail("Invalid email"), ServerValidation(email_server)],
        # Passwords
        "password": [HasLength(min=8, error="Min 8 chars"), IsNotEmpty("Required")],
        "confirm": [MatchesField("password", "Passwords do not match")],
        # Age: numeric range (18-99)
        "age": [IsInRange(min=18, max=99, error="18-99 only")],
        # PIN: exact length 4
        "pin": [HasLength(exact=4, error="4 digits")],
        # JSON string validity
        "json": [IsJSONString("Must be valid JSON")],
        # HTML non-empty (e.g., "<p>hi</p>" ok, "<p></p>" not)
        "bioHtml": [IsNotEmptyHTML("Please provide some content")],
    }

    return Card(p="md", withBorder=True)[
        Stack(gap="md")[
            Title("Complex Form Demo", order=3),
            ValidationModeToggle(st),
            Divider(),
            st.Form(
                initialValues=initial_values,
                mode="controlled",
                validateInputOnBlur=st.mode == "blur",
                validateInputOnChange=st.mode == "change",
                clearInputErrorOnChange=True,
                onSubmitPreventDefault=True,
                validate=validate,
                debounceMs=st.debounce,
                method="post",
                action="/submit",
            )[
                Stack(gap="sm")[
                    Group(gap="md")[
                        TextInput(
                            name="username",
                            label="Username",
                            placeholder="john_doe",
                            withAsterisk=True,
                        ),
                        TextInput(
                            name="email",
                            label="Email",
                            placeholder="you@example.com",
                            withAsterisk=True,
                        ),
                        PasswordInput(
                            name="password", label="Password", withAsterisk=True
                        ),
                        PasswordInput(
                            name="confirm",
                            label="Confirm password",
                            withAsterisk=True,
                        ),
                    ],
                    Group(gap="md")[
                        Checkbox(name="newsletter", label="Subscribe to newsletter"),
                        Select(
                            name="role",
                            label="Role",
                            data=[
                                {"label": "User", "value": "user"},
                                {"label": "Admin", "value": "admin"},
                            ],
                            withAsterisk=True,
                        ),
                        TextInput(
                            name="age",
                            label="Age",
                            placeholder="e.g. 28",
                        ),
                        TextInput(name="pin", label="PIN", placeholder="4 digits"),
                    ],
                    Group(gap="md")[
                        TextInput(
                            name="json",
                            label="JSON",
                            placeholder='{"a": 1}',
                        ),
                        TextInput(
                            name="bioHtml",
                            label="Bio (HTML)",
                            placeholder="<p>Tell us about you</p>",
                        ),
                    ],
                    Divider(label="Addresses"),
                    Stack(gap="xs")[
                        ps.For(
                            range(st.addresses_len),
                            lambda i: Group(key=str(i), gap="sm", align="end")[
                                TextInput(
                                    name=f"addresses.{i}.street",
                                    label=f"Street #{i + 1}",
                                    placeholder="123 Main St",
                                ),
                                TextInput(
                                    name=f"addresses.{i}.city",
                                    label="City",
                                    placeholder="Paris",
                                ),
                                Button(
                                    "Remove",
                                    variant="light",
                                    onClick=lambda: st.remove_address(i),
                                ),
                            ],
                        ),
                        Group(gap="sm")[
                            Button("Add address", onClick=st.add_address),
                            Button(
                                "Remove last", variant="light", onClick=st.remove_last
                            ),
                        ],
                    ],
                    Divider(),
                    Group(gap="sm")[
                        Button(
                            "Simulate errors",
                            variant="light",
                            onClick=st.simulate_errors,
                        ),
                        Button(
                            "Validate (client)", onClick=lambda: st._form.validate()
                        ),
                        Button(
                            "Reset",
                            variant="light",
                            onClick=lambda: st._form.reset(initial_values),
                        ),
                        Button("Submit", type="submit"),
                    ],
                ],
            ],
        ]
    ]


@ps.Component
def MantineLayout():
    return MantineProvider(ps.Outlet())


app = ps.App(
    [ps.Layout(MantineLayout, [ps.Route("/", ComplexFormDemo)])],
)
