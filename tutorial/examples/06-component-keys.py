"examples/06-component-keys.py"

import pulse as ps


class ListState(ps.State):
	items: list[dict]
	new_label: str = ""

	def __init__(self):
		self.items = [
			{"id": 1, "label": "First"},
			{"id": 2, "label": "Second"},
		]

	def prepend(self):
		next_id = max([i["id"] for i in self.items], default=0) + 1
		self.items.insert(0, {"id": next_id, "label": f"Item {next_id}"})

	def remove(self, tid: int):
		self.items = [i for i in self.items if i["id"] != tid]


class ItemState(ps.State):
	checked: bool = False
	note: str = ""


@ps.component
def Item(label: str, onRemove, key=None):
	state = ps.states(ItemState)
	return ps.div(className="flex items-center mb-2")[
		ps.input(
			type="checkbox",
			checked=state.checked,
			onChange=lambda: setattr(state, "checked", not state.checked),
			className="mr-2",
		),
		ps.input(
			type="text",
			value=state.note,
			onChange=lambda e: setattr(state, "note", e["target"]["value"]),
			placeholder="note...",
			className="border p-1 mr-2",
		),
		ps.span(label, className="mr-2"),
		ps.button(
			"Remove",
			onClick=onRemove,
			className="px-2 py-1 border border-red-600 text-red-600 rounded hover:bg-red-600 hover:text-white",
		),
	]


@ps.component
def KeysDemo():
	state = ps.states(ListState)
	# Prepend new items to the beginning to demonstrate diffing
	controls = ps.div(className="mb-4")[
		ps.button(
			"Prepend item",
			onClick=state.prepend,
			className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded mr-3",
		),
	]

	# Unkeyed: internal state will shift when items are prepended
	unkeyed = ps.div(className="p-3 border rounded mr-6")[
		ps.h4("Unkeyed (state will shift)"),
		[
			Item(
				item["label"],
				onRemove=lambda tid=item["id"]: state.remove(tid),
			)
			for item in state.items
		],
	]

	# Keyed: internal state stays with the same logical item
	keyed = ps.div(className="p-3 border rounded")[
		ps.h4("Keyed (state preserved)"),
		[
			Item(
				item["label"],
				onRemove=lambda tid=item["id"]: state.remove(tid),
				key=item["id"],  # critical difference
			)
			for item in state.items
		],
	]

	return ps.div(
		className="w-fit mx-auto h-screen flex flex-col justify-center items-start"
	)[
		ps.h3("Keys vs. No Keys"),
		controls,
		ps.div(unkeyed, keyed, className="flex"),
	]


app = ps.App(
	routes=[ps.Route("/", KeysDemo)],
)
