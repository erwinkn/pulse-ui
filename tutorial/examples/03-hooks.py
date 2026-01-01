"examples/03-hooks.py"

import pulse as ps


class CounterState(ps.State):
	count: int = 0

	def increment(self):
		self.count += 1

	def decrement(self):
		self.count -= 1


class DebugState(ps.State):
	enabled: bool = True

	def __init__(self, enabled: bool):
		self.enabled = enabled

	def toggle(self):
		self.enabled = not self.enabled


def setup_demo(arg, *, kwarg):
	print(f"Received argument: {arg} and kwarg: {kwarg}")
	# do anything else here
	return DebugState(True)


def render_counter(label: str, state: CounterState):
	return ps.div(className="flex items-center gap-2")[
		ps.button(
			"-",
			onClick=state.decrement,
			className="px-2 py-1 bg-red-500 text-white rounded",
		),
		ps.span(f"{label}: {state.count}"),
		ps.button(
			"+",
			onClick=state.increment,
			className="px-2 py-1 bg-green-500 text-white rounded",
		),
	]


def debug_toggle(label: str, state: DebugState):
	return ps.label(className="flex items-center gap-2")[
		ps.input(type="checkbox", checked=state.enabled, onChange=state.toggle),
		f"{label}: {state.enabled}",
	]


@ps.component
def HooksDemo():
	# Use `ps.init()` to create state that persists across renders.
	# Any variables assigned inside the block are captured on the first render
	# and restored on subsequent renders.
	with ps.init():
		counter1 = CounterState()
		counter2 = CounterState()
		debug1 = DebugState(False)

	# `ps.setup` can also be used to create states and perform anything else you
	# need to set up on the first render. Note that the setup function has to be
	# synchronous, it is not recommended to perform async operations, like
	# network requests, there.
	debug2 = ps.setup(setup_demo, "arg", kwarg="kwarg")

	return ps.div(
		className="w-xl mx-auto h-screen flex flex-col justify-center items-start"
	)[
		ps.h3("Setup + States demo", className="text-2xl font-bold mb-4"),
		ps.div(className="space-y-4")[
			render_counter("Counter 1", counter1),
			render_counter("Counter 2", counter2),
			ps.div(className="flex flex-col gap-2")[
				debug_toggle("Debug 1", debug1), debug_toggle("Debug 2", debug2)
			],
		],
	]


app = ps.App(
	routes=[ps.Route("/", HooksDemo)],
)
