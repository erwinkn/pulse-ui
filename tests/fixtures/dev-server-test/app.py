import pulse as ps


class Counter(ps.State):
	count: int = 0

	def increment(self):
		self.count += 1

	def decrement(self):
		self.count -= 1


@ps.component
def CounterApp():
	with ps.init():
		state = Counter()

	return ps.div(
		className="min-h-screen bg-white p-8 flex items-center justify-center"
	)[
		ps.div(className="space-y-4")[
			ps.h1("Counter", className="text-3xl font-bold"),
			ps.div(className="text-4xl font-bold text-center")[str(state.count)],
			ps.div(className="flex gap-2")[
				ps.button(
					"Decrement",
					onClick=lambda: state.decrement(),
					className="px-4 py-2 bg-red-500 text-white rounded",
				),
				ps.button(
					"Increment",
					onClick=lambda: state.increment(),
					className="px-4 py-2 bg-green-500 text-white rounded",
				),
			],
		],
	]


app = ps.App([ps.Route("/", CounterApp)])
