import pulse as ps
from pulse_mantine import Button, Group, MantineProvider, Stack, Text, Title

ps.CssImport("@mantine/core/styles.css")
styles = ps.CssImport("./mantine-demo.module.css", module=True, relative=True)


@ps.component
def CssModulesShowcase():
	return MantineProvider()[
		Stack(gap="md", className=styles.container)[
			Title(order=3, className=styles.title)["Pulse + Mantine"],
			Text(className=styles.description)[
				"This card combines Mantine components with a CSS module "
				"loaded via ps.css_module(). The classes resolve on the client "
				"side, so you can ship scoped styles alongside your views."
			],
			Group(className=styles.actions)[
				Button("Primary action", className=styles.primaryButton),
				Button(
					"Outline action",
					variant="outline",
					className=styles.outlineButton,
				),
			],
			Text(size="xs", className=styles.tagline)[
				"Styled with Mantine + CSS modules"
			],
		]
	]


app = ps.App([ps.Route("/", CssModulesShowcase)])
