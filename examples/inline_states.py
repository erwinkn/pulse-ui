# pyright: reportUnusedFunction=false, reportMissingParameterType=false
"""
Inline State Caching Demo
=========================
Demonstrates ps.state() usage inside components with:
1. Conditional states - states inside if/else blocks
2. Loop states with keys - states in for loops using the `key` parameter
3. Dynamic keys - reinitialize state when key changes
"""

import pulse as ps
from pulse.js import console
from pulse.render_session import run_js


class NoteState(ps.State):
	label: str
	count: int

	def __init__(self, label: str):
		self.label = label
		self.count = 0

	def increment(self):
		self.count += 1

	def reset(self):
		self.count = 0


class CounterState(ps.State):
	count: int

	def __init__(self):
		self.count = 0

	def increment(self):
		self.count += 1


class DemoState(ps.State):
	show_counter: bool = True
	items: list[str]
	key_version: int
	log: list[str]

	def __init__(self):
		self.items = ["alpha", "beta", "gamma"]
		self.key_version = 1
		self.log = []

	def append_log(self, message: str):
		self.log = [*self.log, message]

	def toggle_counter(self):
		self.show_counter = not self.show_counter
		self.append_log(f"toggle_counter -> {self.show_counter}")

	def add_item(self):
		item = f"item-{len(self.items)}"
		self.items = [*self.items, item]
		self.append_log(f"add_item {item}")

	def remove_item(self):
		if self.items:
			removed = self.items[-1]
			self.items = self.items[:-1]
			self.append_log(f"remove_item {removed}")

	def bump_key(self):
		self.key_version += 1
		self.append_log(f"bump_key -> v{self.key_version}")


# Conditional State Demo
# ----------------------
# States inside conditionals are cached by code location.
# When the conditional is false, the state is not disposed.


@ps.component
def ConditionalStateDemo():
	with ps.init():
		state = DemoState()

	if state.show_counter:
		counter_state = ps.state(CounterState())  # pyright: ignore[reportCallIssue]
	else:
		counter_state = None

	def increment_counter():
		if counter_state:
			counter_state.increment()
			state.append_log(f"counter_state -> {counter_state.count}")

	return ps.div(
		ps.h2("Conditional State", className="text-xl font-bold mb-4"),
		ps.p(
			"The states below are created once and reused across renders. They are not disposed when hidden.",
			className="text-gray-600 mb-4",
		),
		ps.div(
			ps.button(
				f"{'Hide' if state.show_counter else 'Show'} Counter",
				onClick=state.toggle_counter,
				className="btn-secondary mr-2",
			),
			ps.button(
				"Increment Counter",
				onClick=increment_counter,
				className="btn-primary mr-2",
				disabled=not state.show_counter,
			),
			ps.span(
				f"Counter: {counter_state.count if counter_state else '—'}",
				className="font-mono",
			),
			className="flex flex-wrap items-center gap-2",
		),
		ps.div(
			ps.p(
				f"Counter state is {'active' if state.show_counter else 'hidden'}",
				className=f"text-sm {'text-green-600' if state.show_counter else 'text-red-600'}",
			),
			ps.p(
				f"Conditional counter value: {counter_state.count if counter_state else '—'}",
				className="text-sm text-gray-600",
			),
			ps.p(
				f"Recent log: {state.log[-1] if state.log else '—'}",
				className="text-xs text-gray-500",
			),
			className="mt-2",
		),
		className="p-4 bg-white rounded shadow mb-6",
	)


# Loop State Demo
# --------------
# States inside a loop must provide a key to disambiguate each instance.


@ps.component
def LoopStateDemo():
	with ps.init():
		state = DemoState()

	items = []
	for item in state.items:
		note = ps.state(lambda item=item: NoteState(item), key=item)
		items.append(
			ps.li(
				ps.span(f"{item}: ", className="font-semibold w-24 inline-block"),
				ps.button(
					"+",
					onClick=note.increment,
					className="btn-primary mr-2",
				),
				ps.button(
					"Reset",
					onClick=note.reset,
					className="btn-secondary mr-2",
				),
				ps.span(f"{note.count}", className="font-mono"),
				className="flex items-center mb-2",
				key=item,
			)
		)

	return ps.div(
		ps.h2("Loop States with Keys", className="text-xl font-bold mb-4"),
		ps.p(
			"Each item has its own state created in a loop. The `key` parameter keeps them unique.",
			className="text-gray-600 mb-4",
		),
		ps.div(
			ps.button(
				"Add Item", onClick=state.add_item, className="btn-secondary mr-2"
			),
			ps.button(
				"Remove Item", onClick=state.remove_item, className="btn-secondary"
			),
			className="mb-4",
		),
		ps.ul(*items, className="list-none"),
		className="p-4 bg-white rounded shadow mb-6",
	)


# Dynamic Key Demo
# ---------------
# When the key changes, a new state instance is created.


@ps.component
def DynamicKeyDemo():
	with ps.init():
		state = DemoState()

	key = f"v{state.key_version}"
	note = ps.state(lambda: NoteState(key), key=key)

	def bump():
		state.bump_key()
		run_js(console.log(f"[dynamic] new key: v{state.key_version}"))
		state.append_log(f"dynamic_key -> v{state.key_version}")

	return ps.div(
		ps.h2("Dynamic Keys", className="text-xl font-bold mb-4"),
		ps.p(
			"Change the key to create a fresh state instance.",
			className="text-gray-600 mb-4",
		),
		ps.div(
			ps.button("Change Key", onClick=bump, className="btn-primary mr-4"),
			ps.button(
				"Increment", onClick=note.increment, className="btn-secondary mr-4"
			),
			ps.span(f"Current key: {key}", className="font-mono mr-4"),
			ps.span(f"Count: {note.count}", className="font-mono"),
			ps.span(
				f"Recent log: {state.log[-1] if state.log else '—'}",
				className="text-xs text-gray-500",
			),
			className="flex flex-wrap items-center",
		),
		className="p-4 bg-white rounded shadow mb-6",
	)


@ps.component
def main_layout():
	return ps.div(
		ps.header(
			ps.h1("Inline State Caching Demo", className="text-2xl font-bold"),
			className="p-4 bg-gray-800 text-white mb-6",
		),
		ps.main(
			ps.p(
				"This example demonstrates ps.state usage inside components with inline caching.",
				className="mb-6 text-gray-700",
			),
			ConditionalStateDemo(),
			LoopStateDemo(),
			DynamicKeyDemo(),
			ps.div(
				ps.h3("How it works", className="text-lg font-semibold mb-2"),
				ps.ul(
					ps.li(
						"States are cached by code location (file + line number)",
						className="mb-1",
					),
					ps.li(
						"In loops, use key= to make each state unique",
						className="mb-1",
					),
					ps.li(
						"Key changes create a new state instance",
						className="mb-1",
					),
					ps.li(
						"Conditional states are kept even when not rendered",
						className="mb-1",
					),
					className="list-disc list-inside text-gray-600",
				),
				className="p-4 bg-gray-50 rounded border",
			),
			className="container mx-auto px-4",
		),
		className="min-h-screen bg-gray-100 text-gray-800",
	)


app = ps.App(
	routes=[
		ps.Route("/", main_layout),
	],
)
