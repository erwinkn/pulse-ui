"examples/05-toggle-component.py"

import pulse as ps


class ToggleState(ps.State):
	on: bool = False

	def toggle(self):
		self.on = not self.on


@ps.component
def Toggle(label: str):
	state = ps.states(ToggleState)
	return ps.div(
		ps.button(
			f"{label}: {'ON' if state.on else 'OFF'}",
			onClick=state.toggle,
			className="px-3 py-1 rounded border",
		),
		ps.small(
			"Enabled content…" if state.on else "", className="block text-gray-500 mt-1"
		),
	)


@ps.component
def ToggleDemo():
	return ps.div(
		ps.h3("Reusable Toggle"),
		ps.div(Toggle(label="Wi‑Fi"), className="mb-2"),
		ps.div(Toggle(label="Bluetooth")),
	)


app = ps.App(
	routes=[ps.Route("/", ToggleDemo)],
)
