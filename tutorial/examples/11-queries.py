import asyncio

import pulse as ps


class QueryDemoState(ps.State):
	user_id: int = 1

	# Unkeyed mode (default), auto-tracks dependencies
	@ps.query(keep_previous_data=True)
	async def user_unkeyed(self) -> dict:
		# Simulate async work
		await asyncio.sleep(1)
		return {"id": self.user_id, "name": f"User {self.user_id}"}

	# Keyed mode, uses explicit dependencies to know when to rerun. This is useful
	@ps.query(keep_previous_data=True)
	async def user_keyed(self) -> dict:
		# Simulate async work
		await asyncio.sleep(1)
		return {"id": self.user_id, "name": f"User {self.user_id}"}

	@user_keyed.key
	def _user_key(self):
		return ("user", self.user_id)


@ps.component
def QueryDemo():
	state = ps.states(QueryDemoState)

	def prev():
		state.user_id = max(1, state.user_id - 1)

	def next_():
		state.user_id = state.user_id + 1

	return ps.div(
		ps.h2("Query Demo", className="text-2xl font-bold mb-4"),
		ps.p(f"User ID: {state.user_id}"),
		ps.div(
			ps.h3("Keyed query", className="text-xl font-semibold mt-4"),
			ps.p(
				"Loading..."
				if state.user_keyed.is_loading
				else f"Data: {state.user_keyed.data}",
				className="mb-2",
			),
			ps.div(
				ps.button(
					"Prev",
					onClick=prev,
					className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 mr-2",
				),
				ps.button(
					"Next",
					onClick=next_,
					className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 mr-2",
				),
				ps.button(
					"Refetch keyed",
					onClick=state.user_keyed.refetch,
					className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600",
				),
				className="mb-4",
			),
			className="mb-6 p-3 rounded bg-white shadow",
		),
		ps.div(
			ps.h3("Unkeyed (auto-tracked) query", className="text-xl font-semibold"),
			ps.p(
				"Loading..."
				if state.user_unkeyed.is_loading
				else f"Data: {state.user_unkeyed.data}",
				className="mb-2",
			),
			ps.div(
				ps.button(
					"Refetch unkeyed",
					onClick=state.user_unkeyed.refetch,
					className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600",
				),
				className="mb-2",
			),
			ps.p(
				"Note: changing User ID will automatically refetch this query without an explicit key.",
				className="text-sm text-gray-600",
			),
			className="p-3 rounded bg-white shadow",
		),
		className="p-4",
	)


app = ps.App(
	routes=[ps.Route("/", QueryDemo)],
)
