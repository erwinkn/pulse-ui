import pulse as ps
from pulse_mantine import (
	AppShell,
	AppShellAside,
	AppShellFooter,
	AppShellHeader,
	AppShellMain,
	AppShellNavbar,
	Group,
	MantineProvider,
	Text,
)
from pulse_mantine.core.navigation.burger import Burger


class State(ps.State):
	opened: bool = False

	def toggle(self):
		self.opened = not self.opened


@ps.component
def Home():
	state = ps.states(State)
	return MantineProvider(
		AppShell(
			header={"height": 60},
			footer={"height": 60},
			navbar={
				"width": 300,
				"breakpoint": "sm",
				"collapsed": {"mobile": not state.opened},
			},
			aside={
				"width": 300,
				"breakpoint": "md",
				"collapsed": {"desktop": False, "mobile": True},
			},
			padding="md",
		)[
			AppShellHeader()[
				Group(h="100%", px="md")[
					Burger(
						opened=state.opened,
						onClick=state.toggle,
						hiddenFrom="sm",
						size="sm",
					),
					"Header",
				]
			],
			AppShellNavbar(p="md")["Navbar"],
			AppShellMain()[
				Text("This is the main section, your app content here."),
				Text(
					"AppShell example with all elements: Navbar, Header, Aside, Footer."
				),
				Text("All elements except AppShell.Main have fixed position."),
				Text(
					"Aside is hidden on on md breakpoint and cannot be opened when it is collapsed"
				),
			],
			AppShellAside(p="md")["Aside"],
			AppShellFooter(p="md")["Footer"],
		]
	)


app = ps.App([ps.Route("/", Home)])
