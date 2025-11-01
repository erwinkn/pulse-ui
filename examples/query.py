import asyncio

import pulse as ps


class UserApi(ps.State):
	user_id: int = 1
	optimistic_name: str | None = None
	success_calls: int = 0
	error_calls: int = 0

	# Keyed query with keep_previous_data default True
	@ps.query(keep_previous_data=True)
	async def user(self):
		print("Running user query")
		await asyncio.sleep(0.3)
		# Simulate API; id 13 fails to demonstrate on_error
		if self.user_id == 13:
			raise RuntimeError("User not found")
		name = self.optimistic_name or f"User {self.user_id}"
		return {"id": self.user_id, "name": name}

	# Key for refetch on id change
	@user.key
	def _user_key(self):
		return ("user", self.user_id)

	# Provide initial data after __init__ (e.g., seeded values)
	@user.initial_data
	def _initial_user(self):
		# Pretend we had a cached snapshot
		return {"id": 0, "name": "<loading>"}

	# Success handler (sync)
	@user.on_success
	def _on_user_success(self):
		self.success_calls += 1

	# Error handler (sync)
	@user.on_error
	def _on_user_error(self):
		self.error_calls += 1

	# Unkeyed query (auto-tracked) using current id
	@ps.query(keep_previous_data=False)
	async def details(self):
		await asyncio.sleep(0.8)
		return {"uppercase": str(self.user_id).upper()}


@ps.component
def QueryExample():
	s = ps.states(UserApi)

	def prev():
		s.user_id = max(1, s.user_id - 1)

	def next_():
		s.user_id = s.user_id + 1

	def set_bad():
		s.user_id = 13

	async def optimistic_rename():
		# Show optimistic change immediately
		s.user.set_data({"id": s.user_id, "name": "Optimistic"})
		# Persist change on server; emulate delay
		await asyncio.sleep(0.4)
		s.optimistic_name = "Optimistic"
		# Refetch to reconcile with server
		s.user.refetch()

	return ps.div(
		ps.h1("Full Query Demo", className="text-2xl font-bold mb-4"),
		ps.div(
			ps.span(f"user_id: {s.user_id}", className="mr-3"),
			ps.button("Prev", onClick=prev, className="btn-secondary mr-2"),
			ps.button("Next", onClick=next_, className="btn-secondary mr-2"),
			ps.button("Make error (id=13)", onClick=set_bad, className="btn-secondary"),
			className="mb-4",
		),
		ps.div(
			ps.h2("Keyed user()", className="text-xl font-semibold mb-2"),
			ps.p(
				"Loading..." if s.user.data is None else f"Data: {s.user.data}",
				className="mb-2",
			),
			ps.p(
				f"error: {type(s.user.error).__name__ if s.user.is_error else '-'}",
				className="text-sm text-red-600 mb-2",
			),
			ps.div(
				ps.button(
					"Refetch",
					onClick=lambda: s.user.refetch(keep_previous_data=False),
					className="btn-primary mr-2",
				),
				ps.button(
					"Optimistic rename",
					onClick=optimistic_rename,
					className="btn-primary",
				),
			),
			ps.p(
				f"on_success calls={s.success_calls} on_error calls={s.error_calls}",
				className="text-xs text-gray-600 mt-2",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		ps.div(
			ps.h2(
				"Unkeyed details() (keep_previous_data=False)",
				className="text-xl font-semibold mb-2",
			),
			ps.p(
				"Loading..." if s.details.is_loading else f"Data: {s.details.data}",
				className="mb-2",
			),
			ps.p(
				"Changes when user_id changes automatically.",
				className="text-xs text-gray-600",
			),
			className="p-3 rounded bg-white shadow",
		),
		className="p-6 space-y-4",
	)


app = ps.App(
	routes=[ps.Route("/", QueryExample)],
)
