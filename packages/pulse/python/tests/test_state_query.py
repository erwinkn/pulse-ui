import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import RouteTree

P = ParamSpec("P")
R = TypeVar("R")


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	"""Set up a PulseContext with an App for all tests."""
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def with_render_session(fn: Callable[P, Awaitable[R]]):
	"""Decorator to wrap test functions with a RenderSession context."""

	async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
		# Create a minimal RouteTree for the session (not needed for query tests)
		routes = RouteTree([])
		session = RenderSession("test-session", routes)
		with ps.PulseContext.update(render=session):
			return await fn(*args, **kwargs)

	return wrapper


@pytest.mark.asyncio
@with_render_session
async def test_state_query_success():
	query_running = False

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			nonlocal query_running
			query_running = True
			await asyncio.sleep(0)
			res = {"id": self.uid}
			query_running = False
			return res

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Initial state is loading until first fetch completes
	assert q.is_loading

	# Wait for query to start
	await asyncio.sleep(0)
	assert query_running
	# Wait for query to complete
	await q.wait()
	assert not query_running
	assert not q.is_loading
	assert not q.is_error
	assert q.data == {"id": s.uid}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch():
	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# First fetch (scheduled on property access)
	await q.wait()
	assert s.calls == 1
	assert q.data == {"id": 1}

	# Manual refetch
	await q.refetch()
	assert q.data == {"id": 1}
	assert s.calls == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_error():
	class S(ps.State):
		flag: int = 0

		@ps.query(retries=0)
		async def fail(self):
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.key
		def _fail_key(self):
			return ("fail", self.flag)

	s = S()
	q = s.fail
	await q.wait()

	assert q.is_loading is False
	assert q.is_error is True
	assert isinstance(q.error, RuntimeError)


@pytest.mark.asyncio
@with_render_session
async def test_state_query_error_refetch():
	class S(ps.State):
		calls: int = 0

		@ps.query(retries=0)
		async def fail(self):
			self.calls += 1
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.key
		def _fail_key(self):
			return ("fail",)

	s = S()
	q = s.fail

	# Refetch after error
	await q.refetch()
	assert q.is_error is True
	assert s.calls == 1

	# Refetch should run again and still error
	await q.refetch()
	assert q.is_error is True
	assert s.calls == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_on_key_change():
	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self):
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# First fetch (scheduled on property access)
	await q.wait()
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Change key; effect should re-run and refetch
	s.uid = 2
	await q.wait()
	assert q.data == {"id": 2}
	assert s.calls == 2


@pytest.mark.asyncio
async def test_state_query_missing_key_defaults_to_auto_tracking():
	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0)
		async def user(self):
			await asyncio.sleep(0)
			return {"id": self.uid}

	s = S()
	q = s.user
	# initial
	await q.wait()
	assert q.data == {"id": 1}
	# change dep -> auto re-run
	s.uid = 2
	await q.wait()
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_manual_set_data():
	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Finish first fetch
	await q.wait()
	assert q.data == {"id": 1}

	# Manual override (optimistic update)
	q.set_data({"id": 999})
	assert q.data == {"id": 999}
	assert q.is_loading is False

	# Trigger refetch; while loading data should remain overridden when keep_previous_data=True
	s.uid = 2
	await asyncio.sleep(0)
	assert q.is_loading is True
	assert q.data == {"id": 999}
	# Complete fetch overwrites data with real value
	await q.wait()
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_manual_set_data_updater():
	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	await q.wait()
	assert q.data == {"id": 1}

	q.set_data(lambda prev: {"id": (prev or {"id": 0})["id"] + 1})
	assert q.data == {"id": 2}
	assert q.is_loading is False


@pytest.mark.asyncio
@with_render_session
async def test_state_query_initial_data_updated_at_staleness():
	now = time.time()

	class S(ps.State):
		@ps.query(stale_time=5)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": 1}

		@user.key
		def _key(self):
			return ("user-initial-stale",)

	s = S()
	q = s.user

	# Set initial data with an old timestamp to make it stale
	q.set_initial_data({"id": 1}, updated_at=now - 10)
	assert q.data == {"id": 1}
	assert q.is_stale() is True

	s2_now = time.time()

	class S2(ps.State):
		@ps.query(stale_time=30)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": 2}

		@user.key
		def _key(self):
			return ("user-initial-fresh",)

	s2 = S2()
	q2 = s2.user

	# Set initial data with current timestamp to keep it fresh
	q2.set_initial_data({"id": 2}, updated_at=s2_now)
	assert q2.is_stale() is False


@pytest.mark.asyncio
@with_render_session
async def test_state_query_set_initial_data_api():
	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _key(self):
			return ("user-set-initial", self.uid)

	s = S()
	q = s.user

	# Seed without fetching
	q.set_initial_data({"id": 123}, updated_at=0)
	assert q.data == {"id": 123}
	assert q.is_stale() is True

	# Next wait should still refetch and replace
	await q.wait()
	assert q.data == {"id": 1}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_set_initial_data_no_effect_after_load():
	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _key(self):
			return ("user-no-effect-after-load", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert q.status == "success"

	# Try to set initial data after query has loaded - should have no effect
	old_data = q.data
	q.set_initial_data({"id": 999}, updated_at=0)
	assert q.data == old_data  # Data should not change
	assert q.data == {"id": 1}  # Should still be the fetched data


@pytest.mark.asyncio
@with_render_session
async def test_state_query_with_initial_value_preserves():
	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self):
			return {"id": 0}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Immediately available initial value, not None
	assert q.data == {"id": 0}
	assert q.status == "success"
	assert q.fetch_status == "fetching"

	# After fetch, data updates
	await q.wait()
	assert q.status == "success"
	assert q.fetch_status == "idle"
	assert q.data == {"id": 1}

	# Disable keep_previous_data -> during refetch, it should reset to None, not initial
	class S2(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=False)
		async def user(self) -> dict[str, int]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self):
			return {"id": -1}

		@user.key
		def _user_key(self):
			# Use a different key to avoid sharing cache with S
			return ("user", self.uid, "S2")

	s2 = S2()
	q2 = s2.user
	assert q2.data == {"id": -1}
	await q2.wait()
	assert q2.data == {"id": 1}

	# change key -> refetch; while loading with keep_previous_data=False, it should reset to None
	# Note: Since initial_data is provided, a new query for the new key starts with that data.
	# So data is NOT None, and is_loading is NOT True.
	s2.uid = 2
	await asyncio.sleep(0)
	assert q2.is_loading is False
	assert q2.is_fetching is True
	assert q2.data == {"id": -1}
	await q2.wait()
	assert q2.is_loading is False
	assert q2.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_initial_data_decorator_uses_value_after_init_and_updates():
	class S(ps.State):
		uid: int = 1
		seed: dict[str, Any] | None = None

		def __init__(self):
			super().__init__()
			# Seed after super().__init__ to ensure decorator reads updated state
			self.seed = {"id": 999}

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self) -> dict[str, Any]:
			# test ensures seed is set before decorator runs; cast for typing
			return self.seed or {"id": -999}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	# initial from decorator, not None
	assert q.data == {"id": 999}
	# With initial data, we are not loading (status is success)
	assert q.is_loading is False
	assert q.is_fetching is True
	# After first fetch, data updates
	await q.wait()
	assert q.is_loading is False
	assert q.data == {"id": 1}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_initial_data_used_on_key_change_when_keep_previous_false():
	"""
	When keep_previous_data=False and initial_data is provided, changing the key
	creates a new query that starts with initial_data (not None), since initial_data
	is used on mount. New key = new query = uses initial_data.
	"""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=False)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self):
			return {"id": -1}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	assert q.data == {"id": -1}
	await q.wait()
	assert q.data == {"id": 1}
	# Change key -> new query starts with initial_data (not None)
	s.uid = 2
	await asyncio.sleep(0)
	assert q.is_loading is False
	assert q.is_fetching is True
	assert q.data == {"id": -1}
	await q.wait()
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_on_success_sync():
	class S(ps.State):
		uid: int = 1
		ok_calls: int = 0
		last: dict[str, Any] | None = None

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.on_success
		def _on_success(self, data: dict[str, Any]):
			self.ok_calls += 1
			self.last = data

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	await q.wait()
	# Wait for on_success
	await asyncio.sleep(0)
	assert q.data == {"id": 1}
	assert s.ok_calls == 1
	assert s.last == {"id": 1}
	s.uid = 2
	await q.wait()
	# Wait for on_success
	await asyncio.sleep(0)
	assert q.data == {"id": 2}
	assert s.ok_calls == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_on_success_async():
	class S(ps.State):
		uid: int = 1
		async_ok_calls: int = 0
		last: dict[str, Any] | None = None

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.on_success
		async def _on_success_async(self, data: dict[str, Any]):
			await asyncio.sleep(0)
			self.async_ok_calls += 1
			self.last = data

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	await q.wait()
	# Wait for on_success (twice, since on_success is async)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert s.async_ok_calls == 1
	assert s.last == {"id": 1}
	assert q.data == {"id": 1}
	s.uid = 2
	await q.wait()
	# Wait for on_success (twice, since on_success is async)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert s.async_ok_calls == 2
	assert s.last == {"id": 2}
	assert q.data == {"id": 2}
	assert s.last == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_on_success_handler_reads_are_untracked():
	class S(ps.State):
		uid: int = 1
		count: int = 0
		seen: list[int] = []

		@ps.computed
		def doubled(self) -> int:
			return self.count * 2

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.on_success
		def _on_success(self, data: dict[str, Any]):
			# read a signal and a computed; should not bind as deps
			_ = self.count
			_ = self.doubled
			self.seen.append(data["id"])  # mutation for verification

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	_ = s.user
	await s.user.wait()
	await asyncio.sleep(0)  # Wait for on_success
	assert s.seen == [1]
	# Change signal/computed inputs; should NOT cause refetch or re-run
	s.count = 5
	# Wait a bit to ensure no refetch happens
	await asyncio.sleep(0)
	# No new success call due to count change
	assert s.seen == [1]
	# Key change still triggers
	s.uid = 2
	await s.user.wait()
	await asyncio.sleep(0)  # Wait for on_success
	assert s.seen == [1, 2]


@pytest.mark.asyncio
@with_render_session
async def test_state_query_on_error_handler_reads_are_untracked():
	class S(ps.State):
		flag: int = 0
		count: int = 0
		hits: int = 0

		@ps.computed
		def doubled(self) -> int:
			return self.count * 2

		@ps.query(retries=0)
		async def fail(self):
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		def _on_error(self, e: Exception):
			_ = self.count
			_ = self.doubled
			self.hits += 1

		@fail.key
		def _fail_key(self):
			return ("fail", self.flag)

	s = S()
	_ = s.fail
	await s.fail.wait()
	await asyncio.sleep(0)  # Wait for on_error
	assert s.hits == 1
	# Changing signals/computeds that were read in handler should not re-run effect
	s.count = 3
	# Wait a bit to ensure no refetch happens
	await asyncio.sleep(0)
	assert s.hits == 1
	# Key change should trigger and run handler again
	s.flag = 1
	await s.fail.wait()
	await asyncio.sleep(0)  # Wait for on_error
	assert s.hits == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_on_error_handler_sync_and_async():
	class S(ps.State):
		calls: int = 0
		err_calls: int = 0
		last_err: Exception | None = None

		@ps.query(retries=0)
		async def fail(self):
			self.calls += 1
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		def _on_error(self, e: Exception):
			self.err_calls += 1
			self.last_err = e

		@fail.key
		def _fail_key(self):
			return ("fail",)

	s = S()
	q = s.fail
	await q.wait()
	await asyncio.sleep(0)  # Wait for on_error
	assert q.is_error is True
	assert s.calls == 1
	assert s.err_calls == 1
	assert isinstance(s.last_err, RuntimeError)
	# Refetch -> handlers run again
	await q.refetch()
	await asyncio.sleep(0)  # Wait for on_error
	assert s.calls == 2
	assert s.err_calls == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_on_error_handler_async_only():
	class S(ps.State):
		calls: int = 0
		async_err_calls: int = 0
		last_err: Exception | None = None

		@ps.query(retries=0)
		async def fail(self):
			self.calls += 1
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		async def _on_error_async(self, e: Exception):
			await asyncio.sleep(0)
			self.async_err_calls += 1
			self.last_err = e

		@fail.key
		def _fail_key(self):
			return ("fail",)

	s = S()
	_ = s.fail
	await s.fail.wait()
	# Wait for on_error (twice, since on_error is async)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert s.calls == 1
	assert s.async_err_calls == 1
	assert isinstance(s.last_err, RuntimeError)
	await s.fail.refetch()
	# Wait for on_error (twice, since on_error is async)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert s.calls == 2
	assert s.async_err_calls == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_gc_time_0_disposes_immediately():
	class S(ps.State):
		uid: int = 1
		started: bool = False
		finished: bool = False

		@ps.query(retries=0, gc_time=0)
		async def user(self) -> dict[str, Any]:
			self.started = True
			# simulate in-flight
			await asyncio.sleep(0)
			self.finished = True
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	_ = s.user

	# Start the task but dispose before it completes
	await asyncio.sleep(0)
	assert s.started is True

	s.dispose()

	assert s.user.__disposed__ is True

	# Allow any scheduled tasks to attempt to finish; they should be canceled
	await asyncio.sleep(0.01)
	assert not s.finished


@pytest.mark.asyncio
@with_render_session
async def test_state_query_gc_time_0_no_refetch_after_state_dispose():
	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Dispose state
	s.dispose()

	# Changing key after dispose must not schedule a new run
	s.uid = 2
	await asyncio.sleep(0.01)
	assert s.calls == 1


@pytest.mark.asyncio
@with_render_session
async def test_query_resets_data_on_key_change_when_keep_previous_false():
	"""
	Regression test: when keep_previous_data=False, changing the query key
	should immediately reset data to None and set is_loading to True,
	synchronously, before the new query runs. This prevents showing stale
	data for one render.
	"""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=False)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert q.is_loading is False

	# Change key - this should synchronously reset data immediately
	s.uid = 2

	# CRITICAL: Check the query result state immediately after key change,
	# but BEFORE any async tasks run. This represents what a render would see.
	# With the bug, this will show stale data. After the fix, it should be cleared.
	await asyncio.sleep(0)  # Allow effect to re-run and check state before query starts
	assert q.is_loading is True, (
		f"Query should be loading immediately after key change, but is_loading={q.is_loading}, data={q.data}"
	)
	assert q.data is None, (
		f"Query data should be cleared immediately after key change, but got {q.data}"
	)

	# Now complete the new query
	await q.wait()

	# After fetch completes, new data should be present
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_query_preserves_data_on_key_change_when_keep_previous_true():
	"""
	Regression test: when keep_previous_data=True, changing the query key
	should set is_loading to True but preserve the previous data,
	synchronously, before the new query runs. This allows showing the old
	data while the new data loads.
	"""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert q.is_loading is False

	# Change key - this should synchronously set loading but preserve data
	s.uid = 2

	# CRITICAL: Check the query result state immediately after key change,
	# but BEFORE any async tasks run. This represents what a render would see.
	# With keep_previous_data=True, should show loading state with old data.
	await asyncio.sleep(0)  # Allow effect to re-run and check state before query starts
	assert q.is_loading is True, (
		f"Query should be loading immediately after key change, but is_loading={q.is_loading}, data={q.data}"
	)
	assert q.data == {"id": 1}, (
		f"Query data should be preserved when keep_previous_data=True, but got {q.data}"
	)

	# Now complete the new query
	await q.wait()

	# After fetch completes, new data should be present and loading should be false
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_invalidate_triggers_refetch():
	"""Test that invalidate() marks query as stale and triggers refetch if there are observers."""

	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Invalidate should trigger refetch
	q.invalidate()
	await q.wait()
	assert q.data == {"id": 1}
	assert s.calls == 2


@pytest.mark.asyncio
@with_render_session
async def test_state_query_invalidate_without_observers_does_not_refetch():
	"""Test that invalidate() without observers does not trigger refetch."""

	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert s.calls == 1

	# Dispose the query result (removes observer)
	q.dispose()

	# Invalidate without observers should not trigger refetch
	q.invalidate()
	await asyncio.sleep(0.01)  # Wait to ensure no refetch happens
	assert s.calls == 1  # Should still be 1


@pytest.mark.asyncio
@with_render_session
async def test_state_query_set_error():
	"""Test that set_error() manually sets error state."""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert q.is_success is True
	assert q.is_error is False

	# Manually set error
	error = ValueError("manual error")
	q.set_error(error)
	assert q.is_error is True
	assert q.is_success is False
	assert q.error == error
	# Data should still be present (set_error doesn't clear data)
	assert q.data == {"id": 1}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_set_error_with_keep_previous_data():
	"""Test that set_error() works correctly with keep_previous_data."""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}

	# Manually set error
	q.set_error(ValueError("manual error"))
	assert q.is_error is True
	assert q.data == {"id": 1}  # Data preserved with keep_previous_data


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_with_cancel_refetch_false():
	"""Test that refetch(cancel_refetch=False) deduplicates concurrent requests."""

	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0.01)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert s.calls == 1

	# Start two refetches with cancel_refetch=False (should deduplicate)
	t1 = asyncio.create_task(q.refetch(cancel_refetch=False))
	t2 = asyncio.create_task(q.refetch(cancel_refetch=False))

	res1 = await t1
	res2 = await t2

	# Should have only run once (deduplicated)
	assert s.calls == 2  # 1 initial + 1 deduplicated refetch
	assert res1 == {"id": 1}
	assert res2 == {"id": 1}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_with_cancel_refetch_true():
	"""Test that refetch(cancel_refetch=True) cancels previous request and starts new one."""

	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0.02)  # Longer delay to ensure cancellation
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	initial_calls = s.calls
	assert initial_calls == 1

	# Start first refetch
	t1 = asyncio.create_task(q.refetch(cancel_refetch=True))
	await asyncio.sleep(0.01)  # Let it start but not complete

	# Start second refetch with cancel_refetch=True (should cancel first)
	t2 = asyncio.create_task(q.refetch(cancel_refetch=True))

	# First might raise CancelledError or return result
	try:
		await t1
	except asyncio.CancelledError:
		pass

	res2 = await t2

	# Should have run at least twice (first may or may not complete before cancellation)
	# The important thing is that cancel_refetch=True allows new request
	assert s.calls >= initial_calls + 1
	assert res2 == {"id": 1}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_multiple_observers_same_query():
	"""Test that multiple QueryResult instances can observe the same query."""

	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s1 = S()
	s2 = S()  # Different state instance, but same key

	q1 = s1.user
	q2 = s2.user  # Should observe the same query due to same key

	# Both should trigger the same query
	await q1.wait()
	assert q1.data == {"id": 1}
	assert s1.calls == 1

	# q2 should see the same data (from cache, same query)
	assert q2.data == {"id": 1}
	assert s2.calls == 0  # Should not have called again (shared query)

	# Refetch from one should update both (same query instance)
	await q1.refetch()
	assert q1.data == {"id": 1}
	assert q2.data == {"id": 1}  # Both see the same query data
	assert s1.calls == 2  # Refetch was called
	assert s2.calls == 0  # Still no call from s2 (shared query)


@pytest.mark.asyncio
@with_render_session
async def test_state_query_multiple_observers_lifecycle():
	"""Test observer lifecycle when multiple observers are added/removed."""

	class S(ps.State):
		uid: int = 1
		calls: int = 0

		@ps.query(retries=0, gc_time=0.1)
		async def user(self) -> dict[str, Any]:
			self.calls += 1
			await asyncio.sleep(0)
			return {"id": self.uid}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s1 = S()
	s2 = S()

	q1 = s1.user
	q2 = s2.user

	# Both observers active
	await q1.wait()
	assert s1.calls == 1

	# Dispose one observer
	q1.dispose()

	# Query should still exist (other observer still active)
	assert q2.data == {"id": 1}

	# Dispose second observer - query should be GC'd
	q2.dispose()
	await asyncio.sleep(0.15)  # Wait for GC

	# New query should be created (old one was GC'd)
	s3 = S()
	q3 = s3.user
	await q3.wait()
	assert s3.calls == 1  # New query, fresh call
