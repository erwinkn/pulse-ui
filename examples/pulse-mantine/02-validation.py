import pulse as ps
from pulse_mantine import (
	Button,
	Card,
	DatePickerInput,
	Group,
	HasLength,
	IsAfter,
	IsBefore,
	IsDate,
	IsEmail,
	IsNotEmpty,
	MantineForm,
	Matches,
	PasswordInput,
	Stack,
	TextInput,
	Title,
)


class FormState(MantineForm):
	def __init__(self) -> None:
		validate = {
			"username": [
				IsNotEmpty("Username is required"),
				HasLength(min=3, max=16, error="3-16 characters"),
				Matches(
					r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"
				),
			],
			"email": IsEmail("Enter a valid email"),
			"password": HasLength(min=8, error="Min 8 characters"),
			"start": IsDate("Pick a start date"),
			"end": [
				IsDate("Pick an end date"),
				IsAfter(
					"start",
					inclusive=True,
					error="End date must be on or after start",
				),
			],
			"deadline": [
				IsDate("Set a deadline"),
				IsBefore("end", error="Deadline must be before the end date"),
				IsAfter("start", error="Deadline must after the start date"),
			],
		}
		super().__init__(
			initialValues={
				"username": "",
				"email": "",
				"password": "",
				"start": None,
				"end": None,
				"deadline": None,
			},
			validate=validate,
		)


@ps.component
def FormValidation():
	form = ps.states(FormState)
	return Card(withBorder=True, shadow="sm", p="lg")[
		Stack(gap="lg")[
			Title("Built-in validators", order=3),
			form.render(onSubmit=lambda values: print("Form data:", values))[
				Stack(gap="md")[
					Group(gap="md")[
						TextInput(
							name="username",
							label="Username",
							placeholder="lowercase letters, numbers, _",
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
					],
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
						DatePickerInput(
							name="deadline",
							label="Deadline",
							placeholder="Pick a deadline",
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


app = ps.App([ps.Route("/", FormValidation)])
