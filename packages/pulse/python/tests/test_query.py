import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import pulse as ps
import pytest
from pulse.queries.query import Query, QueryResult
from pulse.queries.store import QueryStore
from pulse.reactive import Computed
from pulse.render_session import RenderSession
from pulse.routing import RouteTree

P = ParamSpec("P")
R = TypeVar("R")


@pytest.mark.asyncio
async def test_query_store_create_and_get():
	store = QueryStore()
	key = ("test", 1)

	async def fetcher():
		return "data"

	# Create new
	entry1 = store.ensure(key, fetcher)
	assert entry1.key == key
	assert store.get(key) is entry1

	# Get existing
	entry2 = store.ensure(key, fetcher)
	assert entry2 is entry1


@pytest.mark.asyncio
async def test_query_entry_lifecycle():
	key = ("test", 1)

	async def fetcher():
		await asyncio.sleep(0)
		return "result"

	entry = Query(key, fetcher)

	# Initial state
	assert entry.status.read() == "loading"
	assert entry.is_fetching.read() is False
	assert entry.data.read() is None
	assert entry.error.read() is None

	# Start fetch
	task = asyncio.create_task(entry.refetch())
	# Let it start
	await asyncio.sleep(0)

	# Check sync loading state (AsyncQueryEffect)
	assert entry.status.read() == "loading"
	assert entry.is_fetching.read() is True

	await task

	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is False
	assert entry.data.read() == "result"
	assert entry.error.read() is None


@pytest.mark.asyncio
async def test_query_entry_error_lifecycle():
	key = ("test", 1)

	async def fetcher():
		await asyncio.sleep(0)
		raise ValueError("oops")

	entry = Query(key, fetcher, retries=0)
	task = asyncio.create_task(entry.refetch())
	await asyncio.sleep(0)

	assert entry.status.read() == "loading"
	assert entry.is_fetching.read() is True

	try:
		await task
	except ValueError:
		pass

	assert entry.status.read() == "error"
	assert entry.is_fetching.read() is False
	assert entry.data.read() is None
	assert isinstance(entry.error.read(), ValueError)


@pytest.mark.asyncio
async def test_query_entry_deduplication():
	key = ("test", 1)
	calls = 0

	async def fetcher():
		nonlocal calls
		calls += 1
		await asyncio.sleep(0.01)
		return calls

	entry = Query(key, fetcher)

	# Start two fetches with deduplication (cancel_refetch=False)
	t1 = asyncio.create_task(entry.refetch(cancel_refetch=False))
	t2 = asyncio.create_task(entry.refetch(cancel_refetch=False))

	res1 = await t1
	res2 = await t2

	# Should have only run once
	assert calls == 1
	assert res1.status == "success"
	assert res1.data == 1
	assert res2.status == "success"
	assert res2.data == 1


@pytest.mark.asyncio
async def test_query_entry_cancel_refetch():
	key = ("test", 1)
	calls = 0

	async def fetcher():
		nonlocal calls
		calls += 1
		try:
			await asyncio.sleep(0.01)
		except asyncio.CancelledError:
			# print("Cancelled!")
			raise
		return calls

	entry = Query(key, fetcher)

	# Start first fetch
	t1 = asyncio.create_task(entry.refetch(cancel_refetch=True))
	await asyncio.sleep(0.01)  # Ensure it starts

	# Start second fetch, should cancel first
	t2 = asyncio.create_task(entry.refetch(cancel_refetch=True))

	# First one might raise CancelledError or return new result depending on implementation details
	# But here we expect fetch() to handle cancellation if it awaited the task,
	# but since we are awaiting the coroutine wrapper from outside, t1 is the wrapper around `await effect.run()`.
	# The effect run cancels the previous task.

	try:
		await t1
	except asyncio.CancelledError:
		pass

	res2 = await t2

	# Should have run twice (started twice), but first was cancelled
	assert calls == 2
	assert res2.status == "success"
	assert res2.data == 2


@pytest.mark.asyncio
async def test_query_store_garbage_collection():
	store = QueryStore()
	key = ("test", 1)

	async def fetcher():
		return "data"

	# Create with short gc_time
	entry = store.ensure(key, fetcher, gc_time=0.01)
	assert store.get(key) is entry

	observer = QueryResult(Computed(lambda: entry, name="test_query"), gc_time=0.01)
	observer.dispose()
	# entry.schedule_gc()

	# Should still be there immediately
	# entry.schedule_gc()
	assert store.get(key) is entry

	# Wait for GC
	await asyncio.sleep(0.02)

	# Should be gone
	assert store.get(key) is None


@pytest.mark.asyncio
async def test_query_entry_gc_time_reconciliation():
	"""
	Verify that gc_time only increases, never decreases.
	If a past observer had a large gc_time, it persists even after removal.
	"""
	entry = Query(("test", 1), lambda: asyncio.sleep(0), gc_time=0.0)

	query_computed = Computed(lambda: entry, name="test_query")
	# QueryResult automatically observes on creation
	obs1 = QueryResult(query_computed, gc_time=10.0)
	assert entry.cfg.gc_time == 10.0

	obs2 = QueryResult(query_computed, gc_time=5.0)
	assert entry.cfg.gc_time == 10.0  # Max of 10.0 and 5.0

	entry.unobserve(obs2)
	# gc_time never decreases, stays at max seen
	assert entry.cfg.gc_time == 10.0

	entry.unobserve(obs1)
	# Still keeps the max seen value
	assert entry.cfg.gc_time == 10.0

	# Adding a larger gc_time increases it further
	obs3 = QueryResult(query_computed, gc_time=20.0)
	assert entry.cfg.gc_time == 20.0

	entry.unobserve(obs3)
	# Still keeps the max
	assert entry.cfg.gc_time == 20.0


@pytest.mark.asyncio
async def test_async_query_effect_sync_loading():
	"""
	Verify that AsyncQueryEffect sets loading status synchronously
	when scheduled, even before the async task runs.
	"""
	key = ("test", 1)

	async def fetcher():
		await asyncio.sleep(0.01)
		return "done"

	entry = Query(key, fetcher)

	# Force is_fetching to False (status is already loading from initial_data=None)
	entry.status.write("success")
	entry.is_fetching.write(False)

	# Schedule effect (like a dependency change would)
	# We need to manually trigger push_change or run
	entry.effect.push_change()

	# Should be LOADING immediately
	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is True

	# Run it to clear
	await entry.effect.run()
	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is False


@pytest.mark.asyncio
async def test_query_retry_success():
	"""Test that query retries on failure and succeeds on retry."""
	key = ("test", 1)
	attempts = 0

	async def fetcher():
		nonlocal attempts
		attempts += 1
		if attempts < 2:
			raise ValueError("temporary failure")
		return "success"

	entry = Query(key, fetcher, retries=3, retry_delay=0.01)
	await entry.refetch()

	assert entry.status.read() == "success"
	assert entry.data.read() == "success"
	assert entry.error.read() is None
	# Retries are reset on success
	assert entry.retries.read() == 0
	assert attempts == 2


@pytest.mark.asyncio
async def test_query_retry_exhausted():
	"""Test that query fails after all retries are exhausted."""
	key = ("test", 1)
	attempts = 0

	async def fetcher():
		nonlocal attempts
		attempts += 1
		raise ValueError(f"failure {attempts}")

	entry = Query(key, fetcher, retries=2, retry_delay=0.01)
	await entry.refetch()

	assert entry.status.read() == "error"
	assert entry.data.read() is None
	error = entry.error.read()
	assert isinstance(error, ValueError)
	assert error.args[0] == "failure 3"  # 1 initial + 2 retries
	# Retry count is preserved on final error for debugging
	assert entry.retries.read() == 2
	retry_reason = entry.retry_reason.read()
	assert isinstance(retry_reason, ValueError)
	assert retry_reason.args[0] == "failure 3"
	assert attempts == 3


@pytest.mark.asyncio
async def test_query_retry_delay():
	"""Test that retry delay is respected between attempts."""
	key = ("test", 1)
	attempts: list[float] = []

	async def fetcher():
		attempts.append(asyncio.get_event_loop().time())
		if len(attempts) < 3:
			raise ValueError("retry")
		return "success"

	entry = Query(key, fetcher, retries=3, retry_delay=0.01)
	await entry.refetch()

	# Check that delays were respected (with some tolerance)
	assert len(attempts) == 3
	assert attempts[1] - attempts[0] >= 0.008  # ~0.01 delay
	assert attempts[2] - attempts[1] >= 0.008  # ~0.01 delay
	assert entry.status.read() == "success"


@pytest.mark.asyncio
async def test_query_no_retries():
	"""Test query with retries=0 fails immediately."""
	key = ("test", 1)
	attempts = 0

	async def fetcher():
		nonlocal attempts
		attempts += 1
		raise ValueError("failure")

	entry = Query(key, fetcher, retries=0, retry_delay=0.01)
	await entry.refetch()

	assert entry.status.read() == "error"
	assert entry.retries.read() == 0
	assert attempts == 1


@pytest.mark.asyncio
async def test_query_retry_tracking():
	"""Test that retry count and reason are tracked correctly."""
	key = ("test", 1)
	errors = [ValueError("error1"), RuntimeError("error2")]

	async def fetcher():
		if len(errors) > 0:
			raise errors.pop(0)
		return "success"

	entry = Query(key, fetcher, retries=3, retry_delay=0.01)
	await entry.refetch()

	# After success, retries should be reset
	assert entry.status.read() == "success"
	assert entry.retries.read() == 0
	assert entry.retry_reason.read() is None

	# Test that retries are preserved on final error
	async def failing_fetcher():
		raise ValueError("final error")

	entry2 = Query(("test", 2), failing_fetcher, retries=2, retry_delay=0.01)
	await entry2.refetch()

	# Retry count should be preserved on final error
	assert entry2.status.read() == "error"
	assert entry2.retries.read() == 2
	retry_reason2 = entry2.retry_reason.read()
	assert isinstance(retry_reason2, ValueError)
	assert retry_reason2.args[0] == "final error"


@pytest.mark.asyncio
async def test_query_retry_cancellation():
	"""Test that cancellation during retry delay propagates correctly."""
	key = ("test", 1)
	attempts = 0

	async def fetcher():
		nonlocal attempts
		attempts += 1
		raise ValueError("failure")

	entry = Query(key, fetcher, retries=3, retry_delay=0.01)
	task = asyncio.create_task(entry.refetch())

	# Cancel during retry delay
	await asyncio.sleep(0.005)
	task.cancel()

	try:
		await task
	except asyncio.CancelledError:
		pass

	# Should be cancelled, not completed
	assert task.cancelled()
	assert attempts == 1  # Only first attempt ran


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
	assert q.is_fetching is True

	# After fetch, data updates
	await q.wait()
	assert q.status == "success"
	assert q.is_fetching is False
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
async def test_unkeyed_query_resets_data_on_dependency_change_when_keep_previous_false():
	"""
	Regression test: when keep_previous_data=False for an unkeyed query,
	changing a dependency should reset data to None while refetching.
	This prevents showing stale data for one render.
	"""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=False)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert q.is_loading is False

	# Change dependency - this should trigger refetch and reset data
	s.uid = 2

	# Allow effect to detect the change and start refetching
	await asyncio.sleep(0)

	# CRITICAL: Check the query result state while refetching.
	# With keep_previous_data=False, data should be None during refetch.
	assert q.is_fetching is True, (
		f"Query should be fetching after dependency change, but is_fetching={q.is_fetching}"
	)
	assert q.data is None, (
		f"Query data should be None when keep_previous_data=False during refetch, but got {q.data}"
	)

	# Now complete the new query
	await q.wait()

	# After fetch completes, new data should be present
	assert q.is_loading is False
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_unkeyed_query_preserves_data_on_dependency_change_when_keep_previous_true():
	"""
	Regression test: when keep_previous_data=True for an unkeyed query,
	changing a dependency should preserve the previous data while refetching.
	"""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, Any]:
			await asyncio.sleep(0)
			return {"id": self.uid}

	s = S()
	q = s.user

	# Complete first fetch
	await q.wait()
	assert q.data == {"id": 1}
	assert q.is_loading is False

	# Change dependency - this should trigger refetch but preserve data
	s.uid = 2

	# Allow effect to detect the change and start refetching
	await asyncio.sleep(0)

	# CRITICAL: Check the query result state while refetching.
	# With keep_previous_data=True, data should be preserved during refetch.
	assert q.is_fetching is True, (
		f"Query should be fetching after dependency change, but is_fetching={q.is_fetching}"
	)
	assert q.data == {"id": 1}, (
		f"Query data should be preserved when keep_previous_data=True, but got {q.data}"
	)

	# Now complete the new query
	await q.wait()

	# After fetch completes, new data should be present
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
	assert res1.status == "success"
	assert res1.data == {"id": 1}
	assert res2.status == "success"
	assert res2.data == {"id": 1}


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
	assert res2.status == "success"
	assert res2.data == {"id": 1}


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


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_interval():
	"""Test that refetch_interval triggers automatic refetches."""

	class S(ps.State):
		calls: int = 0

		@ps.query(retries=0, refetch_interval=0.05)
		async def data(self) -> int:
			self.calls += 1
			await asyncio.sleep(0)
			return self.calls

		@data.key
		def _data_key(self):
			return ("interval-data",)

	s = S()
	q = s.data

	# Initial fetch
	await q.wait()
	assert s.calls == 1
	assert q.data == 1

	# Wait for interval to trigger refetch
	await asyncio.sleep(0.08)
	assert s.calls == 2
	assert q.data == 2

	# Wait for another interval
	await asyncio.sleep(0.06)
	assert s.calls == 3
	assert q.data == 3

	# Dispose should stop the interval
	q.dispose()
	await asyncio.sleep(0.08)
	assert s.calls == 3  # No more refetches


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_interval_stops_on_dispose():
	"""Test that refetch_interval stops when query is disposed."""

	class S(ps.State):
		calls: int = 0

		@ps.query(retries=0, refetch_interval=0.05)
		async def data(self) -> int:
			self.calls += 1
			await asyncio.sleep(0)
			return self.calls

		@data.key
		def _data_key(self):
			return ("interval-dispose",)

	s = S()
	q = s.data

	# Initial fetch
	await q.wait()
	assert s.calls == 1

	# Wait for one interval refetch
	await asyncio.sleep(0.08)
	assert s.calls == 2

	# Dispose - interval should stop
	q.dispose()
	calls_at_dispose = s.calls

	# Wait and verify no more refetches
	await asyncio.sleep(0.1)
	assert s.calls == calls_at_dispose
