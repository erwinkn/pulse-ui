import pulse as ps


class Items(ps.State):
	items: list[dict]

	def __init__(self):
		self.items = [
			{"id": 1, "label": "A"},
			{"id": 2, "label": "B"},
			{"id": 3, "label": "C"},
		]

	def remove(self, tid: int):
		print(f"Removing item {tid}")
		self.items = [i for i in self.items if i["id"] != tid]


@ps.component
def LateBindingDemo():
	with ps.init():
		state1 = Items()
		state2 = Items()

	bad = ps.div(className="p-3 border rounded mr-6")[
		ps.h4("Bad (late-bound closures)"),
		ps.div(
			[
				ps.button(
					f"Remove {item['label']}",
					# late-bound: all point to last item
					onClick=lambda: state1.remove(item["id"]),  # noqa: B023
					className="mr-2 px-2 py-1 border rounded bg-blue-600 hover:bg-blue-700 text-white",
				)
				for item in state1.items
			]
		),
		ps.p(f"Items: {[i['label'] for i in state1.items]}"),
	]

	good = ps.div(className="p-3 border rounded")[
		ps.h4("Good (uses ps.For)"),
		ps.div(
			ps.For(
				state2.items,
				lambda item: ps.button(
					f"Remove {item['label']}",
					onClick=lambda: state2.remove(item["id"]),
					className="mr-2 px-2 py-1 border rounded bg-blue-600 hover:bg-blue-700 text-white",
				),
			)
		),
		ps.p(f"Items: {[i['label'] for i in state2.items]}"),
	]

	return ps.div(
		className="w-xl mx-auto h-screen flex flex-col justify-center items-start"
	)[
		ps.h3("Late binding in Python loops"),
		ps.div(bad, good, className="grid grid-cols-2 h-38"),
	]


app = ps.App(
	routes=[ps.Route("/", LateBindingDemo)],
)
