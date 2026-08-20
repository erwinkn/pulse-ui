import pulse as ps


class GlobalCounter(ps.State):
	count: int = 0

	def __init__(self, label: str):
		self._label: str = label

	def inc(self):
		self.count += 1

	def dec(self):
		self.count -= 1


# Accessors. Both are scoped to the render session (one browser tab):
# - session_counter(): one instance for the whole session
# - room_counter(id): one instance per id, still within the session
session_counter = ps.global_state(GlobalCounter)
room_counter = ps.global_state(GlobalCounter)


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
	room = ps.route()["pathParams"].get("room")

	# One instance for the whole session
	a = session_counter(label="Session")

	# One instance per room, within this session; default to "global"
	room_id = room or "global"
	b = room_counter(room_id, label="Room")

	return ps.div(
		ps.h1("Global State Demo", className="text-2xl font-bold mb-4"),
		ps.p(
			"Both counters are isolated per browser session. Open a second tab to see "
			"that nothing is shared. The second counter is keyed by room, so navigating "
			"between rooms switches instances while keeping each room's count.",
			className="text-sm text-gray-600 mb-4",
		),
		ps.div(
			ps.span(f"server: {server}", className="mr-3"),
			className="text-xs text-gray-500 mb-4",
		),
		ps.div(
			CounterRow("Session Counter (one per session)", a),
			CounterRow(f"Room Counter (id={room_id})", b),
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
