from typing import Any, Literal, cast

import pulse as ps
from pulse.components.react_router import Link
from pulse_mantine import (
	AllowedFileTypes,
	Button,
	Card,
	Checkbox,
	DatePickerInput,
	DatesProvider,
	DateTimePicker,
	EndsWith,
	FileInput,
	Group,
	HasLength,
	IsAfter,
	IsBefore,
	IsDate,
	IsEmail,
	IsInRange,
	IsInteger,
	IsJSONString,
	IsNotEmpty,
	IsNumber,
	IsULID,
	IsUrl,
	IsUUID,
	MantineProvider,
	Matches,
	MatchesField,
	MaxFileSize,
	MaxItems,
	MinItems,
	MonthPickerInput,
	PasswordInput,
	RequiredUnless,
	RequiredWhen,
	Select,
	ServerValidation,
	Stack,
	StartsWith,
	Text,
	Textarea,
	TextInput,
	TimeInput,
	Title,
	Validation,
)
from pulse_mantine.form.form import MantineForm

NAV_ITEMS = [
	{"label": "Validation modes", "to": "/"},
	{"label": "Built-in rules", "to": "/validators"},
	{"label": "Server validation (async)", "to": "/server"},
	{"label": "File uploads", "to": "/files"},
	{"label": "Dates", "to": "/dates"},
]


class ValidationModesForm(MantineForm):
	def __init__(self, validation_mode: Literal["submit", "blur", "change"]) -> None:
		validate: Validation = {
			"username": [
				IsNotEmpty("Username is required"),
				HasLength(min=3, max=16, error="3-16 characters"),
				Matches(
					r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"
				),
				ServerValidation(
					lambda value, values, path: (
						"This username is reserved"
						if str(value).strip().lower() == "admin"
						else None
					),
					debounce_ms=300,
				),
			],
			"email": [IsEmail("Enter a valid email")],
			"password": [HasLength(min=8, error="Min 8 characters")],
			"confirm": [MatchesField("password", "Passwords do not match")],
			"role": [IsNotEmpty("Choose a role")],
		}
		super().__init__(
			initialValues=VALIDATION_INITIAL_VALUES,
			validate=validate,
			mode="controlled",
			validateInputOnBlur=validation_mode == "blur",
			validateInputOnChange=validation_mode == "change",
			clearInputErrorOnChange=True,
		)


class BuiltInValidatorsForm(MantineForm):
	referral_opt_in: bool = False

	def __init__(self) -> None:
		validate: Validation = {
			"name": [IsNotEmpty("Tell us your name")],
			"email": [IsEmail("Enter a valid email")],
			"website": [IsUrl(error="Include http(s)://")],
			"uuid": [IsUUID(version=4, error="Use a UUID v4 string")],
			"ulid": [IsULID("ULID should be 26 chars")],
			"age": [
				IsNumber("Enter a number"),
				IsInRange(min=18, max=120, error="18-120"),
			],
			"lucky": [IsInteger("Whole number only")],
			"json": [IsJSONString("Provide valid JSON")],
			"slug": [Matches(r"^[a-z0-9-]+$", error="Only lowercase, numbers and -")],
			"promo": [
				EndsWith(
					"-2024", case_sensitive=False, error="Use code ending with -2024"
				)
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
		super().__init__(
			initialValues=BUILT_IN_INITIAL_VALUES,
			validate=validate,
			clearInputErrorOnChange=True,
		)

	def set_referral(self, checked: bool) -> None:
		self.referral_opt_in = checked
		self.set_field_value("referralOptIn", checked)


class AsyncServerValidationForm(MantineForm):
	def __init__(self) -> None:
		async def username_available(
			value: str, values: dict[str, Any], path: str
		) -> str | None:
			# Simulate I/O latency
			import asyncio

			await asyncio.sleep(0.15)
			if not isinstance(value, str):
				return None
			taken = {"admin", "root", "system"}
			return (
				"This username is reserved" if value.strip().lower() in taken else None
			)

		validate: Validation = {
			"username": [
				IsNotEmpty("Username is required"),
				HasLength(min=3, max=16, error="3-16 characters"),
				Matches(
					r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"
				),
				# Async server validator runs on blur only; client runs on change
				ServerValidation(username_available, debounce_ms=150, run_on="blur"),
			],
			"email": [IsEmail("Enter a valid email")],
		}
		super().__init__(
			initialValues={"username": "", "email": ""},
			validate=validate,
			mode="controlled",
			validateInputOnBlur=True,
			validateInputOnChange=True,
			clearInputErrorOnChange=True,
			debounceMs=200,
		)


@ps.component
def ServerValidationPage():
	with ps.init():
		form = AsyncServerValidationForm()

	return Card(withBorder=True, shadow="sm", p="lg")[
		Stack(gap="lg")[
			Stack(gap="xs")[
				Title("Async server validation on blur", order=3),
				Text(
					"Client validators run on change for instant feedback; server checks run on blur.",
				),
			],
			form.render(onSubmit=lambda data: print("Form data:", data))[
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
					Group(gap="sm")[
						Button("Validate now", variant="light", onClick=form.validate),
						Button("Submit", type="submit"),
					],
				]
			],
		]
	]


class FileUploadsForm(MantineForm):
	def __init__(self) -> None:
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
		super().__init__(
			initialValues=FILE_INITIAL_VALUES,
			validate=validate,
			mode="controlled",
		)


class DatesState(MantineForm):
	def __init__(self) -> None:
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
				IsAfter("start", error="Deadline must after the start date"),
			],
			"reminder": [IsNotEmpty("Choose a reminder time")],
			"month": [IsNotEmpty("Pick a month")],
		}
		super().__init__(
			initialValues=DATE_INITIAL_VALUES,
			validate=validate,
			clearInputErrorOnChange=True,
		)


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
	"role": "",
}


@ps.component
def ValidationModesPage():
	raw = ps.route().pathParams.get("mode", "submit")
	mode_str = str(raw or "submit")
	if mode_str not in ("submit", "blur", "change"):
		mode_str = "submit"
	mode = cast(Literal["submit", "blur", "change"], mode_str)
	with ps.init():
		form = ValidationModesForm(validation_mode=mode)

	return Card(withBorder=True, shadow="sm", p="lg")[
		Stack(gap="lg")[
			Stack(gap="xs")[
				Title("Validation modes", order=3),
				Text(
					"Toggle how the form validates fields globally or for specific inputs."
				),
				Group(gap="xs", wrap="wrap")[
					Link("Submit only", to="/submit", className="text-sm"),
					Link("Blur everywhere", to="/blur", className="text-sm"),
					Link("Change everywhere", to="/change", className="text-sm"),
				],
			],
			form.render(
				onSubmit=lambda data: print("Form data:", summarize_form_payload(data))
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
						Button("Validate now", variant="light", onClick=form.validate),
						Button(
							"Reset",
							variant="default",
							onClick=lambda: form.reset(VALIDATION_INITIAL_VALUES),
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
	with ps.init():
		form = BuiltInValidatorsForm()

	return Card(withBorder=True, shadow="sm", p="lg")[
		Stack(gap="lg")[
			Stack(gap="xs")[
				Title("Built-in validation rules", order=3),
				Text(
					"Most of the Mantine client-side rules are available directly from Python."
				),
			],
			form.render(onSubmit=lambda data: print("Form data:", data))[
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
							checked=form.referral_opt_in,
							onChange=lambda event: form.set_referral(
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
						Button("Validate now", variant="light", onClick=form.validate),
						Button(
							"Reset",
							variant="default",
							onClick=lambda: form.reset(BUILT_IN_INITIAL_VALUES),
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
	with ps.init():
		form = FileUploadsForm()

	return Card(withBorder=True, shadow="sm", p="lg")[
		Stack(gap="lg")[
			Stack(gap="xs")[
				Title("File uploads", order=3),
				Text(
					"File inputs stay in sync with the form controller and reuse the same validators."
				),
			],
			form.render(onSubmit=lambda data: print("Form data:", data))[
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
						Button("Validate now", variant="light", onClick=form.validate),
						Button(
							"Reset",
							variant="default",
							onClick=lambda: form.reset(FILE_INITIAL_VALUES),
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
	with ps.init():
		form = DatesState()

	return Card(withBorder=True, shadow="sm", p="lg")[
		Stack(gap="lg")[
			Stack(gap="xs")[
				Title("Date inputs", order=3),
				Text(
					"The Mantine date pickers integrate with Pulse forms automatically."
				),
			],
			DatesProvider(settings={"locale": "en", "firstDayOfWeek": 1})[
				form.render(onSubmit=lambda data: print("Form data:", data))[
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
								"Validate now", variant="light", onClick=form.validate
							),
							Button(
								"Reset",
								variant="default",
								onClick=lambda: form.reset(DATE_INITIAL_VALUES),
							),
							Button("Submit", type="submit"),
						],
					]
				]
			],
		]
	]


def summarize_form_value(value: Any) -> Any:
	if isinstance(value, ps.UploadFile):
		return {
			"filename": value.filename,
			"content_type": value.content_type,
			"size": value.size,
		}
	return value


def summarize_form_payload(data: ps.FormData) -> dict[str, Any]:
	summary: dict[str, Any] = {}
	for key, value in data.items():
		if isinstance(value, list):
			summary[key] = [summarize_form_value(item) for item in value]
		else:
			summary[key] = summarize_form_value(value)
	return summary


app = ps.App(
	[
		ps.Layout(
			MantineLayout,
			[
				ps.Route("/:mode?", ValidationModesPage),
				ps.Route("/validators", BuiltInValidatorsPage),
				ps.Route("/server", ServerValidationPage),
				ps.Route("/files", FileUploadsPage),
				ps.Route("/dates", DatesPage),
			],
		)
	]
)
