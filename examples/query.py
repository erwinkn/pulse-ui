import asyncio
import time
from typing import TypedDict

import pulse as ps


class UserData(TypedDict):
	id: int
	name: str


class DetailsData(TypedDict):
	uppercase: str


class UserProfileData(TypedDict):
	id: int
	profile: str
	timestamp: float


class UserPermissionsData(TypedDict):
	id: int
	permissions: list[str]


class UserStatusData(TypedDict):
	id: int
	status: str
	last_seen: float


class UpdateUserNameResult(TypedDict):
	success: bool
	new_name: str


class DeleteUserResult(TypedDict):
	deleted: bool


class UserApi(ps.State):
	user_id: int = 1
	optimistic_name: str | None = None
	success_calls: int = 0
	error_calls: int = 0
	mutation_success_calls: int = 0
	mutation_error_calls: int = 0

	# Keyed query with keep_previous_data default True
	@ps.query(keep_previous_data=False)
	async def user(self) -> UserData:
		print("Running user query")
		await asyncio.sleep(0.5)
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
	def _initial_user(self) -> UserData:
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
	async def details(self) -> DetailsData:
		await asyncio.sleep(0.8)
		return {"uppercase": str(self.user_id).upper()}

	# Query with custom stale_time (data considered fresh for 5 seconds)
	@ps.query(stale_time=5.0, keep_previous_data=True)
	async def user_profile(self) -> UserProfileData:
		print("Running user profile query")
		await asyncio.sleep(0.2)
		return {
			"id": self.user_id,
			"profile": f"Profile for user {self.user_id}",
			"timestamp": time.time(),
		}

	@user_profile.key
	def _user_profile_key(self):
		return ("user_profile", self.user_id)

	# Query with custom retry configuration
	@ps.query(retries=5, retry_delay=1.0, gc_time=60.0)
	async def user_permissions(self) -> UserPermissionsData:
		print("Running user permissions query")
		await asyncio.sleep(0.1)
		# Simulate occasional failure for retry demonstration
		if self.user_id == 99:
			# Check retry count from the query's internal state
			# For demo purposes, we'll just fail once
			pass
		return {"id": self.user_id, "permissions": ["read", "write"]}

	@user_permissions.key
	def _user_permissions_key(self):
		return ("user_permissions", self.user_id)

	# Query with no retries for fast-failing operations
	@ps.query(retries=0)
	async def user_status(self) -> UserStatusData:
		print("Running user status query")
		await asyncio.sleep(0.05)
		return {"id": self.user_id, "status": "active", "last_seen": time.time()}

	@user_status.key
	def _user_status_key(self):
		return ("user_status", self.user_id)

	# Mutation example - update user name
	@ps.mutation
	async def update_user_name(self, new_name: str) -> UpdateUserNameResult:
		print(f"Updating user {self.user_id} name to {new_name}")
		await asyncio.sleep(0.5)
		# Simulate server update
		self.optimistic_name = new_name
		# Invalidate related queries
		self.user.invalidate()
		self.user_profile.invalidate()
		return {"success": True, "new_name": new_name}

	@update_user_name.on_success
	def _on_update_success(self, result: UpdateUserNameResult):
		self.mutation_success_calls += 1
		print(f"Mutation succeeded: {result}")

	@update_user_name.on_error
	def _on_update_error(self, error: Exception):
		self.mutation_error_calls += 1
		print(f"Mutation failed: {error}")

	# Mutation that can fail
	@ps.mutation
	async def delete_user(self) -> DeleteUserResult:
		print(f"Deleting user {self.user_id}")
		await asyncio.sleep(0.3)
		if self.user_id == 1:
			raise RuntimeError("Cannot delete admin user")
		return {"deleted": True}

	@delete_user.on_error
	def _on_delete_error(self, error: Exception):
		print(f"Delete failed: {error}")


@ps.component
def QueryExample():
	s = ps.states(UserApi)

	def prev():
		s.user_id = max(1, s.user_id - 1)

	def next_():
		s.user_id = s.user_id + 1

	def set_bad():
		s.user_id = 13

	def set_retry_demo():
		s.user_id = 99

	async def optimistic_rename():
		# Show optimistic change immediately
		s.user.set_data({"id": s.user_id, "name": "Optimistic"})
		# Persist change on server; emulate delay
		await asyncio.sleep(0.4)
		s.optimistic_name = "Optimistic"
		# Refetch to reconcile with server
		await s.user.refetch()

	async def manual_set_data():
		# Manually set data without triggering a fetch
		s.user.set_data({"id": s.user_id, "name": "Manually Set"})

	async def invalidate_all():
		# Invalidate all queries to force refetch
		s.user.invalidate()
		s.user_profile.invalidate()
		s.user_permissions.invalidate()
		s.user_status.invalidate()

	async def update_name():
		# Use mutation to update name
		await s.update_user_name("Updated Name")

	async def delete_current():
		# Try to delete current user (will fail for user 1)
		try:
			await s.delete_user()
		except Exception:
			pass  # Error handled by mutation callback

	async def wait_for_data():
		# Demonstrate wait() functionality
		print("Waiting for user data...")
		data = await s.user.wait()
		print(f"Got data: {data}")

	return ps.div(
		ps.h1("Full Query Demo", className="text-2xl font-bold mb-4"),
		ps.div(
			ps.span(f"user_id: {s.user_id}", className="mr-3"),
			ps.button("Prev", onClick=prev, className="btn-secondary mr-2"),
			ps.button("Next", onClick=next_, className="btn-secondary mr-2"),
			ps.button(
				"Make error (id=13)", onClick=set_bad, className="btn-secondary mr-2"
			),
			ps.button(
				"Retry demo (id=99)", onClick=set_retry_demo, className="btn-secondary"
			),
			className="mb-4",
		),
		# Query Status Properties Demo
		ps.div(
			ps.h2("Query Status Properties", className="text-xl font-semibold mb-2"),
			ps.div(
				ps.p(f"Status: {s.user.status}", className="mb-1"),
				ps.p(f"is_fetching: {s.user.is_fetching}", className="mb-1"),
				ps.p(f"is_loading: {s.user.is_loading}", className="mb-1"),
				ps.p(f"is_success: {s.user.is_success}", className="mb-1"),
				ps.p(f"is_error: {s.user.is_error}", className="mb-1"),
				ps.p(f"is_fetching: {s.user.is_fetching}", className="mb-1"),
				ps.p(f"Error: {s.user.error}", className="mb-1 text-red-600"),
				className="text-sm font-mono bg-gray-100 p-2 rounded",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		# Keyed user() query
		ps.div(
			ps.h2("Keyed user() - Basic Query", className="text-xl font-semibold mb-2"),
			ps.p(
				"Loading..." if s.user.data is None else f"Data: {s.user.data}",
				className="mb-2",
			),
			ps.div(
				ps.button(
					"Refetch",
					onClick=lambda: s.user.refetch(),
					className="btn-primary mr-2",
				),
				ps.button(
					"Optimistic rename",
					onClick=optimistic_rename,
					className="btn-primary mr-2",
				),
				ps.button(
					"Manual set data",
					onClick=manual_set_data,
					className="btn-secondary mr-2",
				),
				ps.button(
					"Invalidate",
					onClick=lambda: s.user.invalidate(),
					className="btn-secondary",
				),
			),
			ps.p(
				f"on_success calls={s.success_calls} on_error calls={s.error_calls}",
				className="text-xs text-gray-600 mt-2",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		# user_profile() with stale_time
		ps.div(
			ps.h2(
				"user_profile() - stale_time=5s", className="text-xl font-semibold mb-2"
			),
			ps.p(
				"Loading..."
				if s.user_profile.is_loading
				else f"Data: {s.user_profile.data}",
				className="mb-2",
			),
			ps.p(
				f"Data is considered stale after 5 seconds. Last fetch: {time.time() - (s.user_profile.data.get('timestamp', 0) if s.user_profile.data else 0):.1f}s ago",
				className="text-xs text-gray-600",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		# user_permissions() with custom retries
		ps.div(
			ps.h2(
				"user_permissions() - retries=5, retry_delay=1s",
				className="text-xl font-semibold mb-2",
			),
			ps.p(
				"Loading..."
				if s.user_permissions.is_loading
				else f"Data: {s.user_permissions.data}",
				className="mb-2",
			),
			ps.p(
				"Set user_id=99 to see retry behavior (simulated network errors)",
				className="text-xs text-gray-600",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		# user_status() with no retries
		ps.div(
			ps.h2(
				"user_status() - retries=0 (fast fail)",
				className="text-xl font-semibold mb-2",
			),
			ps.p(
				"Loading..."
				if s.user_status.is_loading
				else f"Data: {s.user_status.data}",
				className="mb-2",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		# Unkeyed details() query
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
			className="p-3 rounded bg-white shadow mb-6",
		),
		# Mutations
		ps.div(
			ps.h2("Mutations", className="text-xl font-semibold mb-2"),
			ps.div(
				ps.button(
					"Update Name (mutation)",
					onClick=update_name,
					className="btn-primary mr-2",
				),
				ps.button(
					"Delete User (will fail for id=1)",
					onClick=delete_current,
					className="btn-danger mr-2",
				),
				ps.button(
					"Wait for Data",
					onClick=wait_for_data,
					className="btn-secondary mr-2",
				),
				ps.button(
					"Invalidate All",
					onClick=invalidate_all,
					className="btn-secondary",
				),
			),
			ps.p(
				f"Mutation success calls: {s.mutation_success_calls}, error calls: {s.mutation_error_calls}",
				className="text-xs text-gray-600 mt-2",
			),
			className="p-3 rounded bg-white shadow mb-6",
		),
		# Session-wide caching demo
		ps.div(
			ps.h2("Session-wide Query Caching", className="text-xl font-semibold mb-2"),
			ps.p(
				"Change user_id and notice how queries with the same key share cached data. "
				+ "Try switching between users to see cache hits.",
				className="text-sm text-gray-600",
			),
			className="p-3 rounded bg-white shadow",
		),
		className="p-6 space-y-4",
	)


app = ps.App(
	routes=[ps.Route("/", QueryExample)],
)
