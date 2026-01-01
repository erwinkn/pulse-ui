"examples/02-counter.py"

import pulse as ps


class CounterState(ps.State):
	count: int = 0

	def increment(self):
		self.count += 1

	def reset(self):
		self.count = 0


@ps.component
def Counter():
	with ps.init():
		state = CounterState()
	print(f"Rendering counter, count is {state.count}")

	def decrement():
		state.count -= 1

	return ps.div(
		className="w-screen h-screen flex flex-col items-center justify-center space-y-4"
	)[
		ps.h2("Interactive Counter", className="text-3xl font-bold"),
		# Display current count
		ps.p(f"Current count: {state.count}", className="text-lg"),
		# Control buttons
		ps.div(className="flex items-center space-x-2")[
			ps.button(
				"Decrement (-1)",
				onClick=decrement,
				className="bg-red-500 text-white px-4 py-2 rounded mr-4 hover:bg-red-600",
			),
			ps.button(
				"Reset (0)",
				onClick=state.reset,
				className="bg-gray-500 text-white px-4 py-2 rounded mr-4 hover:bg-gray-600",
			),
			ps.button(
				"Increment (+1)",
				onClick=state.increment,
				className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600",
			),
		],
	]


app = ps.App(
	routes=[ps.Route("/", Counter)],
)
