import pulse as ps


class CounterState(ps.State):
	count: int = 0

	def increment(self):
		self.count += 1

	def decrement(self):
		self.count -= 1


@ps.component
def Counter():
	# Executes on first render. The print statements executes only once. On
	# subsequent renders, local variables are populated from the results of the
	# first execution.
	with ps.init():
		print("Running init block")
		state = CounterState()

	return ps.div()[
		ps.p(f"Count: {state.count}"),
		ps.button("Increment", onClick=state.increment),
		ps.button("Decrement", onClick=state.decrement),
	]


app = ps.App([ps.Route("/", Counter)])
