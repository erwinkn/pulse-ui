import pulse as ps
from pulse_mantine import (
	Button,
	Center,
	Checkbox,
	Container,
	Group,
	IsEmail,
	MantineForm,
	TextInput,
)


@ps.component
def Demo():
	with ps.init():
		form = MantineForm(
			initialValues={"email": "", "termsOfService": False},
			validate={
				# Equivalent to Mantine's built-in `isEmail` validator
				"email": IsEmail("Invalid email")
			},
		)

	async def printFormValues():
		values = await form.get_form_values()
		print("Form values:", values)

	return Center(h="100vh")[
		Container(size="lg")[
			# `MantineForm.render` accepts all the regular <form> attributes
			form.render(
				# Will print `{ "email": "your@email.com", "termsOfService": True, }`
				onSubmit=lambda values: print(values),
			)[
				TextInput(
					# Setting the name will register this field like
					# `{...form.getInputProps('email')}` in the original example
					name="email",
					withAsterisk=True,
					label="Email",
					placeholder="your@email.com",
				),
				Checkbox(
					# Same thing, registers as the "termsOfService" field
					name="termsOfService",
					mt="md",
					label="I agree to sell my privacy",
				),
				Group(justify="flex-end", mt="md")[
					Button("Get form values", onClick=printFormValues),
					Button("Submit", type="submit"),
				],
			]
		]
	]


app = ps.App([ps.Route("/", Demo)])
