import pulse as ps


class GlobalCounter(ps.State):
	count: int = 0

	def __init__(self, label: str):
		self._label = label

	def inc(self):
		self.count += 1

	def dec(self):
		self.count -= 1


# Accessors
# - session_counter(): per-session singleton
# - shared_counter(id): cross-session shared by id
session_counter = ps.global_state(GlobalCounter)
shared_counter = ps.global_state(GlobalCounter)


@ps.component
def CounterRow(title: str, counter: GlobalCounter):
	return ps.div(
		ps.h3(title, className="text-lg font-semibold mb-2"),
		ps.div(
			ps.button("-", onClick=counter.dec, className="btn-secondary mr-3"),
			ps.span(str(counter.count), className="font-mono text-xl"),
			ps.button("+", onClick=counter.inc, className="btn-primary ml-3"),
			className="flex items-center",
		),
		className="p-3 rounded border bg-white",
	)


@ps.component
def GlobalStateDemo():
	server = ps.server_address()
	room = ps.route().pathParams.get("room")

	# Per-session singleton
	a = session_counter(label="Session")

	# Shared across sessions by id; default to "global" when no room provided
	shared_id = room or "global"
	b = shared_counter(shared_id, label="Shared")

	return ps.div(
		ps.h1("Global State Demo", className="text-2xl font-bold mb-4"),
		ps.p(
			"Session-local counters are isolated per browser session. Shared counters are keyed by id.",
			className="text-sm text-gray-600 mb-4",
		),
		ps.div(
			ps.span(f"server: {server}", className="mr-3"),
			className="text-xs text-gray-500 mb-4",
		),
		ps.div(
			CounterRow("Session Counter (isolated)", a),
			CounterRow(f"Shared Counter (id={shared_id})", b),
			className="grid gap-4 max-w-xl",
		),
		ps.div(
			ps.p("Routes:", className="mt-6 font-semibold"),
			ps.ul(
				ps.li(ps.Link("/", to="/", className="link")),
				ps.li(
					ps.Link(
						"/room1",
						to="/room1",
						className="link",
					)
				),
				ps.li(
					ps.Link(
						"/room2",
						to="/room2",
						className="link",
					)
				),
				className="list-disc list-inside text-sm text-gray-700",
			),
		),
		className="p-6",
	)


app = ps.App(
	routes=[
		ps.Route("/", GlobalStateDemo),
		ps.Route("/:room", GlobalStateDemo),
	],
)
