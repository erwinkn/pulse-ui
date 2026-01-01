"examples/10-batch-updates.py"

import asyncio

import pulse as ps


class CounterState(ps.State):
	count: int = 0

	async def increment_twice(self):
		await asyncio.sleep(1)
		# Two separate state updates.
		# They are automatically batched, the app only rerenders once.
		self.count += 1
		self.count += 1
		await asyncio.sleep(1)
		# The app rerenders again after these two updates
		self.count += 1
		self.count += 1


@ps.component
def Counter():
	with ps.init():
		state = CounterState()

	return ps.div(
		className="w-screen h-screen flex flex-col items-center justify-center space-y-4"
	)[
		ps.h2("Interactive Counter", className="text-3xl font-bold"),
		# Display current count
		ps.p(f"Current count: {state.count}", className="text-lg"),
		# Control buttons
		ps.div(className="flex items-center space-x-2")[
			ps.button(
				"Increment with delay (+2, +2)",
				onClick=state.increment_twice,
				className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600",
			),
		],
	]


app = ps.App(
	routes=[ps.Route("/", Counter)],
)
