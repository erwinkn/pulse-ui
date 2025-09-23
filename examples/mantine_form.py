import pulse as ps
from pulse.components.react_router import Link
from pulse_mantine import (
    MantineProvider,
    Card,
    Stack,
    Title,
    Text,
    Group,
    SegmentedControl,
    Checkbox,
    TextInput,
    PasswordInput,
    Select,
    Button,
    Divider,
    FileInput,
    Textarea,
)
from pulse_mantine import (
    DatesProvider,
    DatePickerInput,
    DateTimePicker,
    MonthPickerInput,
    TimeInput,
)
from pulse_mantine import Form
from pulse_mantine.form import (
    Validation,
    IsEmail,
    IsNotEmpty,
    HasLength,
    Matches,
    MatchesField,
    IsInRange,
    IsJSONString,
    IsUrl,
    IsUUID,
    IsULID,
    IsNumber,
    IsInteger,
    StartsWith,
    EndsWith,
    RequiredWhen,
    RequiredUnless,
    AllowedFileTypes,
    MaxFileSize,
    MinItems,
    MaxItems,
    IsDate,
    IsAfter,
    IsBefore,
)


NAV_ITEMS = [
    {"label": "Validation modes", "to": "/"},
    {"label": "Built-in rules", "to": "/validators"},
    {"label": "File uploads", "to": "/files"},
    {"label": "Dates", "to": "/dates"},
]


def format_setting(value: object) -> str:
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(v) for v in value) + "]"
    if value is None:
        return "None"
    return str(value)


class BaseFormState(ps.State):
    def __init__(self) -> None:
        self._form = Form()

    @property
    def Form(self):
        return self._form.Component

    def reset(self, values: dict | None = None) -> None:
        self._form.reset(values)

    def validate_now(self) -> None:
        self._form.validate()


class ValidationModesState(BaseFormState):
    blur_mode = "submit"
    change_mode = "global"
    clear_on_change: bool = True

    def __init__(self) -> None:
        super().__init__()

    def set_blur_mode(self, value: str) -> None:
        self.blur_mode = value

    def set_change_mode(self, value: str) -> None:
        self.change_mode = value

    def set_clear_flag(self, checked: bool) -> None:
        self.clear_on_change = checked

    @staticmethod
    def mode_value(option: str):
        if option == "global":
            return True
        if option == "email":
            return ["email"]
        return False


class BuiltInValidatorsState(BaseFormState):
    referral_opt_in: bool = False

    def __init__(self) -> None:
        super().__init__()

    def set_referral(self, checked: bool) -> None:
        self.referral_opt_in = checked
        self._form.set_field_value("referralOptIn", checked)


class FileUploadsState(BaseFormState):
    def __init__(self) -> None:
        super().__init__()


class DatesState(BaseFormState):
    def __init__(self) -> None:
        super().__init__()


@ps.component
def Navigation():
    return Group(gap="sm", wrap="wrap")[
        ps.For(
            NAV_ITEMS,
            lambda item: Link(
                item["label"],
                key=item["to"],
                to=item["to"],
                className="px-3 py-2 rounded-md border border-gray-200 text-sm font-medium hover:bg-gray-50",
            ),
        )
    ]


@ps.Component
def MantineLayout():
    return MantineProvider(
        Stack(gap="xl", p="xl")[
            Card(withBorder=True, shadow="sm", p="lg")[
                Stack(gap="sm")[
                    Title("Pulse Mantine form showcase", order=2),
                    Text("Explore focused examples of the Python integration."),
                    Navigation(),
                ]
            ],
            ps.Outlet(),
        ]
    )


VALIDATION_INITIAL_VALUES = {
    "username": "",
    "email": "",
    "password": "",
    "confirm": "",
    "role": "user",
}


@ps.component
def ValidationModesPage():
    st = ps.states(ValidationModesState)
    blur_setting = ValidationModesState.mode_value(st.blur_mode)
    change_setting = ValidationModesState.mode_value(st.change_mode)

    validate: Validation = {
        "username": [
            IsNotEmpty("Username is required"),
            HasLength(min=3, max=16, error="3-16 characters"),
            Matches(r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"),
        ],
        "email": [IsEmail("Enter a valid email")],
        "password": [HasLength(min=8, error="Min 8 characters")],
        "confirm": [MatchesField("password", "Passwords do not match")],
        "role": [IsNotEmpty("Choose a role")],
    }

    form_component = st.Form

    return Card(withBorder=True, shadow="sm", p="lg")[
        Stack(gap="lg")[
            Stack(gap="xs")[
                Title("Validation modes", order=3),
                Text(
                    "Toggle how the form validates fields globally or for specific inputs."
                ),
            ],
            Stack(gap="sm")[
                Text("validateInputOnBlur"),
                SegmentedControl(
                    value=st.blur_mode,
                    data=[
                        {"label": "Submit only", "value": "submit"},
                        {"label": "Blur everywhere", "value": "global"},
                        {"label": "Blur email only", "value": "email"},
                    ],
                    onChange=lambda value: st.set_blur_mode(value),
                ),
                Text(format_setting(blur_setting)),
            ],
            Stack(gap="sm")[
                Text("validateInputOnChange"),
                SegmentedControl(
                    value=st.change_mode,
                    data=[
                        {"label": "Off", "value": "submit"},
                        {"label": "All fields", "value": "global"},
                        {"label": "Email only", "value": "email"},
                    ],
                    onChange=lambda value: st.set_change_mode(value),
                ),
                Text(format_setting(change_setting)),
            ],
            Checkbox(
                label="clearInputErrorOnChange",
                checked=st.clear_on_change,
                onChange=lambda event: st.set_clear_flag(event["target"]["checked"]),
            ),
            Divider(),
            form_component(
                initialValues=VALIDATION_INITIAL_VALUES,
                validate=validate,
                mode="controlled",
                validateInputOnBlur=blur_setting,
                validateInputOnChange=change_setting,
                clearInputErrorOnChange=st.clear_on_change,
                onSubmitPreventDefault=True,
                onSubmit=lambda data: print("Form data:", data),
            )[
                Stack(gap="md")[
                    Group(gap="md")[
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
                    ],
                    Group(gap="md")[
                        PasswordInput(
                            name="password",
                            label="Password",
                            placeholder="At least 8 characters",
                            withAsterisk=True,
                        ),
                        PasswordInput(
                            name="confirm",
                            label="Confirm password",
                            withAsterisk=True,
                        ),
                        Select(
                            name="role",
                            label="Role",
                            data=[
                                {"label": "User", "value": "user"},
                                {"label": "Admin", "value": "admin"},
                                {"label": "Viewer", "value": "viewer"},
                            ],
                            withAsterisk=True,
                        ),
                    ],
                    Group(gap="sm")[
                        Button(
                            "Validate now", variant="light", onClick=st.validate_now
                        ),
                        Button(
                            "Reset",
                            variant="default",
                            onClick=lambda: st.reset(VALIDATION_INITIAL_VALUES),
                        ),
                        Button("Submit", type="submit"),
                    ],
                ]
            ],
        ]
    ]


BUILT_IN_INITIAL_VALUES = {
    "name": "",
    "email": "",
    "website": "",
    "uuid": "",
    "ulid": "",
    "age": "",
    "lucky": "",
    "json": "",
    "slug": "",
    "promo": "",
    "referral": "",
    "employmentStatus": "employed",
    "company": "",
    "referralOptIn": False,
    "referralCode": "",
}


@ps.component
def BuiltInValidatorsPage():
    st = ps.states(BuiltInValidatorsState)

    validate: Validation = {
        "name": [IsNotEmpty("Tell us your name")],
        "email": [IsEmail("Enter a valid email")],
        "website": [
            IsUrl(error="Include http(s)://"),
        ],
        "uuid": [IsUUID(version=4, error="Use a UUID v4 string")],
        "ulid": [IsULID("ULID should be 26 chars")],
        "age": [IsNumber("Enter a number"), IsInRange(min=18, max=120, error="18-120")],
        "lucky": [IsInteger("Whole number only")],
        "json": [IsJSONString("Provide valid JSON")],
        "slug": [Matches(r"^[a-z0-9-]+$", error="Only lowercase, numbers and -")],
        "promo": [
            EndsWith("-2024", case_sensitive=False, error="Use code ending with -2024")
        ],
        "referral": [
            StartsWith("REF-", case_sensitive=False, error="Codes start with REF-")
        ],
        "company": [
            RequiredUnless(
                "employmentStatus",
                equals="freelancer",
                error="Provide a company unless you're a freelancer",
            )
        ],
        "referralCode": [
            RequiredWhen(
                "referralOptIn", truthy=True, error="Enter your referral code"
            ),
            StartsWith("RC-", error="Codes start with RC-"),
        ],
    }

    form_component = st.Form

    return Card(withBorder=True, shadow="sm", p="lg")[
        Stack(gap="lg")[
            Stack(gap="xs")[
                Title("Built-in validation rules", order=3),
                Text(
                    "Most of the Mantine client-side rules are available directly from Python."
                ),
            ],
            form_component(
                initialValues=BUILT_IN_INITIAL_VALUES,
                validate=validate,
                onSubmitPreventDefault=True,
                clearInputErrorOnChange=True,
                onSubmit=lambda data: print("Submitted data:", data),
            )[
                Stack(gap="md")[
                    Group(gap="md")[
                        TextInput(name="name", label="Name", withAsterisk=True),
                        TextInput(name="email", label="Email", withAsterisk=True),
                        TextInput(
                            name="website",
                            label="Website",
                            placeholder="https://example.com",
                        ),
                    ],
                    Group(gap="md")[
                        TextInput(name="uuid", label="UUID v4"),
                        TextInput(name="ulid", label="ULID"),
                        TextInput(
                            name="slug", label="Slug", placeholder="lowercase-text"
                        ),
                    ],
                    Group(gap="md")[
                        TextInput(name="age", label="Age"),
                        TextInput(name="lucky", label="Lucky number"),
                        Textarea(name="json", label="JSON payload", minRows=2),
                    ],
                    Group(gap="md")[
                        TextInput(
                            name="promo", label="Promo code", placeholder="summer-2024"
                        ),
                        TextInput(name="referral", label="Referral code"),
                    ],
                    Group(gap="md")[
                        Select(
                            name="employmentStatus",
                            label="Employment status",
                            data=[
                                {"label": "Employed", "value": "employed"},
                                {"label": "Freelancer", "value": "freelancer"},
                                {"label": "Student", "value": "student"},
                            ],
                        ),
                        TextInput(name="company", label="Company"),
                    ],
                    Group(gap="md", align="end")[
                        Checkbox(
                            label="I have a referral code",
                            checked=st.referral_opt_in,
                            onChange=lambda event: st.set_referral(
                                event["target"]["checked"]
                            ),
                        ),
                        TextInput(
                            name="referralCode",
                            label="Referral code",
                            placeholder="RC-XXXX",
                        ),
                    ],
                    Group(gap="sm")[
                        Button(
                            "Validate now", variant="light", onClick=st.validate_now
                        ),
                        Button(
                            "Reset",
                            variant="default",
                            onClick=lambda: st.reset(BUILT_IN_INITIAL_VALUES),
                        ),
                        Button("Submit", type="submit"),
                    ],
                ]
            ],
        ]
    ]


FILE_INITIAL_VALUES = {
    "resume": None,
    "portfolio": [],
}


@ps.component
def FileUploadsPage():
    st = ps.states(FileUploadsState)

    validate: Validation = {
        "resume": [
            IsNotEmpty("Upload at least one resume"),
            AllowedFileTypes(
                extensions=["pdf", "doc", "docx"], error="PDF or Word only"
            ),
            MaxFileSize(5 * 1024 * 1024, error="Max 5MB"),
        ],
        "portfolio": [
            MinItems(1, error="Upload at least one project"),
            MaxItems(5, error="Up to 5 files"),
            AllowedFileTypes(mime_types=["image/*"], error="Images only"),
            MaxFileSize(8 * 1024 * 1024, error="Max 8MB each"),
        ],
    }

    return Card(withBorder=True, shadow="sm", p="lg")[
        Stack(gap="lg")[
            Stack(gap="xs")[
                Title("File uploads", order=3),
                Text(
                    "File inputs stay in sync with the form controller and reuse the same validators."
                ),
            ],
            st.Form(
                initialValues=FILE_INITIAL_VALUES,
                validate=validate,
                onSubmitPreventDefault=True,
                mode="controlled",
                onSubmit=lambda data: print("Form data:", format_json(data)),
            )[
                Stack(gap="md")[
                    FileInput(
                        name="resume",
                        label="Resume",
                        placeholder="Upload resume",
                        withAsterisk=True,
                    ),
                    FileInput(
                        name="portfolio",
                        label="Portfolio images",
                        placeholder="Upload screenshots",
                        multiple=True,
                        clearable=True,
                        accept="image/png,image/jpeg",
                    ),
                    Group(gap="sm")[
                        Button(
                            "Validate now", variant="light", onClick=st.validate_now
                        ),
                        Button(
                            "Reset",
                            variant="default",
                            onClick=lambda: st.reset(FILE_INITIAL_VALUES),
                        ),
                        Button("Submit", type="submit"),
                    ],
                ]
            ],
        ]
    ]


DATE_INITIAL_VALUES = {
    "start": None,
    "end": None,
    "deadline": None,
    "reminder": "",
    "month": None,
}


@ps.component
def DatesPage():
    st = ps.states(DatesState)

    validate: Validation = {
        "start": [IsDate("Pick a start date")],
        "end": [
            IsDate("Pick an end date"),
            IsAfter(
                "start", inclusive=True, error="End date must be on or after start"
            ),
        ],
        "deadline": [
            IsDate("Set a deadline"),
            IsBefore("end", error="Deadline must be before the end date"),
        ],
        "reminder": [IsNotEmpty("Choose a reminder time")],
        "month": [IsNotEmpty("Pick a month")],
    }

    form_component = st.Form

    return Card(withBorder=True, shadow="sm", p="lg")[
        Stack(gap="lg")[
            Stack(gap="xs")[
                Title("Date inputs", order=3),
                Text(
                    "The Mantine date pickers integrate with Pulse forms automatically."
                ),
            ],
            DatesProvider(settings={"locale": "en", "firstDayOfWeek": 1})[
                form_component(
                    initialValues=DATE_INITIAL_VALUES,
                    validate=validate,
                    onSubmitPreventDefault=True,
                    clearInputErrorOnChange=True,
                )[
                    Stack(gap="md")[
                        Group(gap="md")[
                            DatePickerInput(
                                name="start",
                                label="Start date",
                                placeholder="Select start",
                                withAsterisk=True,
                            ),
                            DatePickerInput(
                                name="end",
                                label="End date",
                                placeholder="Select end",
                                withAsterisk=True,
                            ),
                        ],
                        Group(gap="md")[
                            DateTimePicker(
                                name="deadline",
                                label="Deadline",
                                placeholder="Pick date & time",
                            ),
                            TimeInput(
                                name="reminder",
                                label="Reminder time",
                                withSeconds=False,
                            ),
                        ],
                        MonthPickerInput(
                            name="month",
                            label="Focus month",
                            placeholder="Select month",
                        ),
                        Group(gap="sm")[
                            Button(
                                "Validate now", variant="light", onClick=st.validate_now
                            ),
                            Button(
                                "Reset",
                                variant="default",
                                onClick=lambda: st.reset(DATE_INITIAL_VALUES),
                            ),
                            Button("Submit", type="submit"),
                        ],
                    ]
                ]
            ],
        ]
    ]


def format_json(data: dict) -> dict:
    def process_value(value):
        if isinstance(value, bytes):
            return "<content>"
        if isinstance(value, dict):
            return {k: process_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [process_value(v) for v in value]
        return value

    return process_value(data)  # pyright: ignore[reportReturnType]


app = ps.App(
    [
        ps.Layout(
            MantineLayout,
            [
                ps.Route("/", ValidationModesPage),
                ps.Route("/validators", BuiltInValidatorsPage),
                ps.Route("/files", FileUploadsPage),
                ps.Route("/dates", DatesPage),
            ],
        )
    ]
)
