from dataclasses import dataclass
from typing import Literal

import pulse as ps

Filter = Literal["all", "open", "done"]


@dataclass
class Todo:
	id: int
	text: str
	done: bool


class TodosState(ps.State):
	todos: list[Todo]
	filt: Filter = "all"
	_owner: str  # non-reactive property

	def __init__(self, owner: str):
		self._owner = owner
		self.todos = [
			Todo(1, "Learn Pulse", False),
			Todo(2, "Ship demo", True),
		]

	def set_filter(self, filt: Filter):
		self.filt = filt

	def add_todo(self, text: str):
		next_id = max((n.id for n in self.todos), default=0) + 1
		self.todos.append(Todo(next_id, text, False))

	def toggle(self, todo_id: int):
		for n in self.todos:
			if n.id == todo_id:
				n.done = not n.done

	@ps.computed
	def filtered(self) -> list[Todo]:
		if self.filt == "open":
			return [n for n in self.todos if not n.done]
		if self.filt == "done":
			return [n for n in self.todos if n.done]
		return self.todos


global_todos = ps.global_state(lambda: TodosState(owner="session"))


@ps.component
def TodosPage():
	state = global_todos()
	return ps.div(className="max-w-md mx-auto p-4")[
		ps.h3(f"Notes ({len(state.filtered)})", className="font-bold mb-2"),
		ps.small(f"Owner: {state._owner}", className="text-gray-500 mb-2 block"),
		ps.div(className="mb-3")[
			ps.button(
				"All",
				onClick=lambda: state.set_filter("all"),
				className="mr-2 "
				+ ("bg-blue-600 text-white px-2" if state.filt == "all" else "px-2"),
			),
			ps.button(
				"Open",
				onClick=lambda: state.set_filter("open"),
				className="mr-2 "
				+ ("bg-blue-600 text-white px-2" if state.filt == "open" else "px-2"),
			),
			ps.button(
				"Done",
				onClick=lambda: state.set_filter("done"),
				className=(
					"bg-blue-600 text-white px-2" if state.filt == "done" else "px-2"
				),
			),
			ps.button(
				"Add sample",
				onClick=lambda: state.add_todo(f"Note {len(state.todos) + 1}"),
				className="ml-3 px-2 border rounded",
			),
		],
		ps.ul(
			[
				ps.li(className="mb-1 flex items-center", key=str(n.id))[
					ps.input(
						type="checkbox",
						checked=n.done,
						onChange=lambda _, nid=n.id: state.toggle(nid),
						className="mr-2",
					),
					ps.span(
						n.text,
						className=("line-through text-gray-500" if n.done else ""),
					),
				]
				for n in state.filtered
			]
		),
	]


app = ps.App(
	routes=[ps.Route("/", TodosPage)],
)
