import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast

import pulse as ps
import pytest
from pulse.helpers import MISSING
from pulse.queries.protocol import QueryResult
from pulse.queries.query import KeyedQuery, KeyedQueryResult, UnkeyedQueryResult
from pulse.queries.store import QueryStore
from pulse.reactive import Computed, Untrack
from pulse.render_session import RenderSession
from pulse.routing import RouteTree
from pulse.test_helpers import wait_for

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


def create_query_with_observer(
	key: tuple[Any, ...],
	fetcher: Callable[[], Awaitable[Any]],
	gc_time: float = 300.0,
	retries: int = 3,
	retry_delay: float = 0.01,
) -> tuple[KeyedQuery[Any], KeyedQueryResult[Any]]:
	"""Helper to create a Query with a QueryResult observer (required for fetch function)."""
	query: KeyedQuery[Any] = KeyedQuery(
		key, gc_time=gc_time, retries=retries, retry_delay=retry_delay
	)
	query_computed = Computed(lambda: query, name=f"test_query({key})")
	result = KeyedQueryResult(query_computed, fetch_fn=fetcher, gc_time=gc_time)
	return query, result


def query_result(q: Any) -> KeyedQueryResult[T] | UnkeyedQueryResult[T]:
	"""Helper for accessing internal methods on concrete query result types."""
	return cast(KeyedQueryResult[T] | UnkeyedQueryResult[T], q)


@pytest.mark.asyncio
async def test_query_store_create_and_get():
	store = QueryStore()
	key = ("test", 1)

	# Create new
	entry1 = store.ensure(key)
	assert entry1.key == key
	assert store.get(key) is entry1

	# Get existing
	entry2 = store.ensure(key)
	assert entry2 is entry1


@pytest.mark.asyncio
async def test_query_store_list_key():
	"""Test that list keys are normalized to tuples and work correctly."""
	store = QueryStore()

	# Create with list key
	entry1 = store.ensure(["test", 1])
	assert entry1.key == ("test", 1)  # Normalized to tuple

	# Get with tuple key finds it
	assert store.get(("test", 1)) is entry1

	# Get with list key also finds it
	assert store.get(["test", 1]) is entry1

	# Ensure with tuple key returns same entry
	entry2 = store.ensure(("test", 1))
	assert entry2 is entry1


@pytest.mark.asyncio
async def test_query_store_rejects_unhashable_key():
	store = QueryStore()

	with pytest.raises(TypeError, match="QueryKey values must be hashable"):
		store.ensure(("test", []))  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_query_entry_lifecycle():
	key = ("test", 1)

	async def fetcher():
		await asyncio.sleep(0)
		return "result"

	entry, observer = create_query_with_observer(key, fetcher)

	# QueryResult automatically starts fetching if stale on mount
	# Wait for initial fetch to complete
	await observer.wait()

	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is False
	assert entry.data.read() == "result"
	assert entry.error.read() is None

	# Refetch and verify cycle
	task = asyncio.create_task(entry.refetch())
	# Let it start
	await asyncio.sleep(0)

	# Check sync loading state (AsyncQueryEffect)
	assert entry.is_fetching.read() is True

	await task

	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is False
	assert entry.data.read() == "result"
	assert entry.error.read() is None


@pytest.mark.asyncio
async def test_query_wait_is_side_effect_free_and_ensure_starts_fetch():
	key = ("test", "ensure")
	calls = 0

	async def fetcher():
		nonlocal calls
		calls += 1
		await asyncio.sleep(0)
		return "result"

	query: KeyedQuery[str] = KeyedQuery(key, retries=0, retry_delay=0.01)
	query_computed = Computed(lambda: query, name="test_query(ensure)")
	observer = KeyedQueryResult(
		query_computed, fetch_fn=fetcher, gc_time=300.0, fetch_on_mount=False
	)

	result = await observer.wait()
	assert calls == 0
	assert observer.is_loading
	assert observer.is_fetching is False
	assert result.status == "success"
	assert result.data is None

	result = await observer.ensure()
	assert result.status == "success"
	assert result.data == "result"
	assert calls == 1


@pytest.mark.asyncio
async def test_unkeyed_query_wait_is_side_effect_free_and_ensure_starts_fetch():
	calls = 0

	class S(ps.State):
		@ps.query(fetch_on_mount=False, retries=0)
		async def value(self) -> int:
			nonlocal calls
			calls += 1
			await asyncio.sleep(0)
			return 42

	s = S()
	q = s.value

	result = await q.wait()
	assert calls == 0
	assert q.is_loading
	assert result.status == "success"
	assert result.data is None

	result = await q.ensure()
	assert result.status == "success"
	assert result.data == 42
	assert calls == 1


@pytest.mark.asyncio
async def test_query_entry_error_lifecycle():
	key = ("test", 1)

	async def fetcher():
		await asyncio.sleep(0)
		raise ValueError("oops")

	entry, observer = create_query_with_observer(key, fetcher, retries=0)

	# Wait for the auto-fetch to complete with error
	try:
		await observer.wait()
	except Exception:
		pass

	assert entry.status.read() == "error"
	assert entry.is_fetching.read() is False
	assert entry.data.read() is MISSING
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

	entry, observer = create_query_with_observer(key, fetcher)
	# Wait for auto-fetch to complete
	await observer.wait()
	assert calls == 1

	# Start two more refetches with deduplication (cancel_refetch=False)
	t1 = asyncio.create_task(entry.refetch(cancel_refetch=False))
	t2 = asyncio.create_task(entry.refetch(cancel_refetch=False))

	res1 = await t1
	res2 = await t2

	# Should have only run once more (total 2)
	assert calls == 2
	assert res1.status == "success"
	assert res1.data == 2
	assert res2.status == "success"
	assert res2.data == 2


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

	entry, observer = create_query_with_observer(key, fetcher)
	# Wait for auto-fetch to complete
	await observer.wait()
	initial_calls = calls

	# Start first fetch
	t1 = asyncio.create_task(entry.refetch(cancel_refetch=True))
	assert await wait_for(lambda: entry.is_fetching.read() is True, timeout=0.2)

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

	# Should have run twice more (started twice), but first was cancelled
	assert calls == initial_calls + 2
	assert res2.status == "success"


@pytest.mark.asyncio
async def test_query_store_garbage_collection():
	store = QueryStore()
	key = ("test", 1)

	async def fetcher():
		return "data"

	# Create with short gc_time
	entry: KeyedQuery[str] = store.ensure(key, gc_time=0.01)
	assert store.get(key) is entry

	observer = KeyedQueryResult(
		Computed(lambda: entry, name="test_query"), fetch_fn=fetcher, gc_time=0.01
	)
	query_result(observer).dispose()
	# entry.schedule_gc()

	# Should still be there immediately
	# entry.schedule_gc()
	assert store.get(key) is entry

	# Wait for GC
	assert await wait_for(lambda: store.get(key) is None, timeout=0.2)

	# Should be gone
	assert store.get(key) is None


@pytest.mark.asyncio
async def test_keyed_query_dispose_cancels_gc():
	async def fetcher():
		return "data"

	entry: KeyedQuery[str] = KeyedQuery(("test", "gc"), gc_time=0.01)
	observer = KeyedQueryResult(
		Computed(lambda: entry, name="test_query(gc)"), fetch_fn=fetcher, gc_time=0.01
	)
	observer.dispose()
	assert entry._gc_handle is not None  # pyright: ignore[reportPrivateUsage]

	try:
		entry.dispose()
		assert entry._gc_handle is None  # pyright: ignore[reportPrivateUsage]
	finally:
		entry.cancel_gc()


@pytest.mark.asyncio
async def test_query_entry_gc_time_reconciliation():
	"""
	Verify that gc_time only increases, never decreases.
	If a past observer had a large gc_time, it persists even after removal.
	"""

	async def dummy_fetcher():
		await asyncio.sleep(0)
		return None

	entry: KeyedQuery[None] = KeyedQuery(("test", 1), gc_time=0.0)

	query_computed = Computed(lambda: entry, name="test_query")
	# QueryResult automatically observes on creation
	obs1 = KeyedQueryResult(query_computed, fetch_fn=dummy_fetcher, gc_time=10.0)
	# Should take max of store's 0 and obs1's 10
	assert entry.cfg.gc_time == 10.0
	obs2 = KeyedQueryResult(query_computed, fetch_fn=dummy_fetcher, gc_time=5.0)
	assert entry.cfg.gc_time == 10.0  # Max of 10.0 and 5.0

	entry.unobserve(obs2)
	# gc_time never decreases, stays at max seen
	assert entry.cfg.gc_time == 10.0

	entry.unobserve(obs1)
	# Still keeps the max seen value
	assert entry.cfg.gc_time == 10.0

	# Adding a larger gc_time increases it further
	obs3 = KeyedQueryResult(query_computed, fetch_fn=dummy_fetcher, gc_time=20.0)
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

	entry, observer = create_query_with_observer(key, fetcher)

	# Wait for initial fetch to complete
	await observer.wait()
	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is False

	# Now invalidate - should synchronously set is_fetching=True before any async tick
	observer.invalidate()

	# Should be LOADING immediately (synchronously, before any await)
	assert entry.status.read() == "success"
	assert entry.is_fetching.read() is True

	# Wait for the refetch to complete
	await entry.wait()
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

	entry, observer = create_query_with_observer(
		key, fetcher, retries=3, retry_delay=0.01
	)
	await observer.refetch()

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

	entry, observer = create_query_with_observer(
		key, fetcher, retries=2, retry_delay=0.01
	)
	await observer.refetch()

	assert entry.status.read() == "error"
	assert entry.data.read() is MISSING
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

	entry, observer = create_query_with_observer(
		key, fetcher, retries=3, retry_delay=0.01
	)
	await observer.refetch()

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

	entry, observer = create_query_with_observer(
		key, fetcher, retries=0, retry_delay=0.01
	)
	await observer.refetch()

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

	entry, observer = create_query_with_observer(
		key, fetcher, retries=3, retry_delay=0.01
	)
	await observer.refetch()

	# After success, retries should be reset
	assert entry.status.read() == "success"
	assert entry.retries.read() == 0
	assert entry.retry_reason.read() is None

	# Test that retries are preserved on final error
	async def failing_fetcher():
		raise ValueError("final error")

	entry2, observer2 = create_query_with_observer(
		("test", 2), failing_fetcher, retries=2, retry_delay=0.01
	)
	await observer2.refetch()

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

	# Use longer retry delay to make timing more reliable
	# Create with fetch_on_mount=False so we control when fetching starts
	query: KeyedQuery[Any] = KeyedQuery(key, gc_time=300.0, retries=3, retry_delay=1.0)
	query_computed = Computed(lambda: query, name=f"test_query({key})")
	observer = KeyedQueryResult(
		query_computed, fetch_fn=fetcher, gc_time=300.0, fetch_on_mount=False
	)

	# Now start a refetch - this will be the first fetch
	task = asyncio.create_task(observer.refetch())

	# Wait for first attempt to complete and enter retry delay
	# The fetcher runs synchronously (no await before the raise), so just give it time to start
	assert await wait_for(
		lambda: attempts == 1 and query.retries.read() == 1, timeout=0.2
	)

	# Now cancel during retry delay
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
async def test_state_query_set_data_visible_during_refetch_with_keep_previous_data():
	fetch_started = asyncio.Event()
	finish_fetch = asyncio.Event()
	calls = 0

	class S(ps.State):
		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, int]:
			nonlocal calls
			calls += 1
			fetch_started.set()
			await finish_fetch.wait()
			return {"id": calls}

		@user.key
		def _user_key(self):
			return ("user",)

	s = S()
	q = s.user

	finish_fetch.set()
	await q.wait()
	assert q.data == {"id": 1}

	finish_fetch.clear()
	fetch_started.clear()

	refetch_task = asyncio.create_task(q.refetch())
	await fetch_started.wait()
	assert q.is_fetching is True

	q.set_data({"id": 999})
	assert q.data == {"id": 999}

	finish_fetch.set()
	await refetch_task
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
async def test_state_query_initial_data_used_on_key_change_when_keep_previous_true():
	"""
	When keep_previous_data=True and initial_data is provided, changing the key
	should use initial_data while the new key fetches.
	"""

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
	assert q.data == {"id": 0}
	await q.wait()
	assert q.data == {"id": 1}

	# Change key -> should use initial_data while fetching new key
	s.uid = 2
	await asyncio.sleep(0)
	assert q.is_fetching is True
	assert q.data == {"id": 0}
	await q.wait()
	assert q.data == {"id": 2}


@pytest.mark.asyncio
@with_render_session
async def test_state_query_previous_none_replaced_with_initial_data_when_keep_previous_true():
	"""
	When keep_previous_data=True and previous data is None, changing the key should
	use initial_data even if previous data is None.
	"""

	class S(ps.State):
		uid: int = 1

		@ps.query(retries=0, keep_previous_data=True)
		async def user(self) -> dict[str, Any] | None:
			await asyncio.sleep(0)
			if self.uid == 1:
				return None
			return {"id": self.uid}

		@user.initial_data
		def _user_initial(self):
			return {"id": 0}

		@user.key
		def _user_key(self):
			return ("user", self.uid)

	s = S()
	q = s.user
	assert q.data == {"id": 0}
	await q.wait()
	assert q.data is None

	s.uid = 2
	await asyncio.sleep(0)
	assert q.is_fetching is True
	assert q.data == {"id": 0}
	await q.wait()
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
async def test_unkeyed_query_on_success_handler_reads_are_untracked():
	"""Test that on_success callbacks in unkeyed queries don't create dependencies."""
	max_fetches = 3  # Guard against infinite loop

	class S(ps.State):
		count: int = 0
		unrelated: int = 0
		success_calls: int = 0

		@ps.computed
		def doubled(self) -> int:
			return self.unrelated * 2

		@ps.query(retries=0)
		async def value(self) -> int:
			self.count += 1
			if self.count > max_fetches:
				raise RuntimeError("Too many fetches - callback dependency bug")
			await asyncio.sleep(0)
			return self.count

		@value.on_success
		def _on_success(self, data: int):
			# Read signals in callback - should NOT be tracked as dependencies
			_ = self.unrelated
			_ = self.doubled
			self.success_calls += 1

	s = S()
	_ = s.value
	await s.value.wait()
	await asyncio.sleep(0)  # Wait for on_success
	assert s.count == 1
	assert s.success_calls == 1

	# Changing signals read in on_success should NOT trigger refetch
	s.unrelated = 5
	# Give time for any (buggy) refetch to trigger
	await asyncio.sleep(0.01)
	# Should NOT have refetched
	assert s.count == 1, "Changing signal read in on_success should not trigger refetch"
	assert s.success_calls == 1


@pytest.mark.asyncio
async def test_unkeyed_query_on_error_handler_reads_are_untracked():
	"""Test that on_error callbacks in unkeyed queries don't create dependencies."""
	max_fetches = 3  # Guard against infinite loop

	class S(ps.State):
		fetch_count: int = 0
		unrelated: int = 0
		error_calls: int = 0

		@ps.computed
		def doubled(self) -> int:
			return self.unrelated * 2

		@ps.query(retries=0)
		async def fail(self) -> int:
			self.fetch_count += 1
			if self.fetch_count > max_fetches:
				raise RuntimeError("Too many fetches - callback dependency bug")
			await asyncio.sleep(0)
			raise RuntimeError("boom")

		@fail.on_error
		def _on_error(self, e: Exception):
			if "Too many fetches" in str(e):
				return  # Don't count the guard error
			# Read signals in callback - should NOT be tracked as dependencies
			_ = self.unrelated
			_ = self.doubled
			self.error_calls += 1

	s = S()
	_ = s.fail
	await s.fail.wait()
	await asyncio.sleep(0)  # Wait for on_error
	assert s.fetch_count == 1
	assert s.error_calls == 1

	# Changing signals read in on_error should NOT trigger refetch
	s.unrelated = 5
	# Give time for any (buggy) refetch to trigger
	await asyncio.sleep(0.01)
	# Should NOT have refetched
	assert s.fetch_count == 1, (
		"Changing signal read in on_error should not trigger refetch"
	)
	assert s.error_calls == 1


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

	assert query_result(s.user).__disposed__ is True

	# Allow any scheduled tasks to attempt to finish; they should be canceled
	assert not await wait_for(lambda: s.finished, timeout=0.05)


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
	assert not await wait_for(lambda: s.calls > 1, timeout=0.05)
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
	query_result(q).dispose()

	# Invalidate without observers should not trigger refetch
	q.invalidate()
	assert not await wait_for(lambda: s.calls > 1, timeout=0.05)
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
	assert await wait_for(lambda: q.is_fetching is True, timeout=0.2)

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

		@ps.query(retries=0, gc_time=0.01)
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
	query_result(q1).dispose()

	# Query should still exist (other observer still active)
	assert q2.data == {"id": 1}

	# Dispose second observer - query should be GC'd
	query_result(q2).dispose()
	key = ("user", 1)
	render = ps.PulseContext.get().render
	assert render is not None
	store = render.query_store
	assert await wait_for(lambda: store.get(key) is None, timeout=0.2)

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

		@ps.query(retries=0, refetch_interval=0.01)
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

	# Wait for interval to trigger refetch and complete
	assert await wait_for(lambda: q.data == 2)
	assert s.calls == 2

	# Wait for another interval
	assert await wait_for(lambda: q.data == 3)
	assert s.calls == 3

	# Dispose should stop the interval
	query_result(q).dispose()
	# Negative test - verify no more refetches happen
	assert not await wait_for(lambda: s.calls > 3, timeout=0.05)
	assert s.calls == 3


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_interval_zero_fetches_on_mount_only():
	"""Test that refetch_interval=0 disables interval but still fetches on mount."""

	class S(ps.State):
		calls: int = 0

		@ps.query(retries=0, refetch_interval=0)
		async def data(self) -> int:
			self.calls += 1
			await asyncio.sleep(0)
			return self.calls

		@data.key
		def _data_key(self):
			return ("interval-zero",)

	s = S()
	q = s.data

	# Auto-fetch should happen on mount
	assert await wait_for(lambda: q.data == 1 and s.calls == 1)

	# No interval refetch should be scheduled
	assert not await wait_for(lambda: s.calls > 1, timeout=0.05)
	assert q.data == 1

	query_result(q).dispose()


@pytest.mark.asyncio
@with_render_session
async def test_state_query_refetch_interval_stops_on_dispose():
	"""Test that refetch_interval stops when query is disposed."""

	class S(ps.State):
		calls: int = 0

		@ps.query(retries=0, refetch_interval=0.01)
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
	assert await wait_for(lambda: s.calls >= 2)

	# Dispose - interval should stop
	query_result(q).dispose()
	calls_at_dispose = s.calls

	# Wait and verify no more refetches (negative test - sleep is appropriate here)
	assert not await wait_for(lambda: s.calls > calls_at_dispose, timeout=0.05)
	assert s.calls == calls_at_dispose


@pytest.mark.asyncio
async def test_keyed_query_interval_uses_min_interval_and_latest_observer():
	"""Interval uses min observer interval and latest observer with that interval."""
	calls_a = 0
	calls_b = 0
	calls_c = 0

	async def fetch_a():
		nonlocal calls_a
		calls_a += 1
		await asyncio.sleep(0)
		return calls_a

	async def fetch_b():
		nonlocal calls_b
		calls_b += 1
		await asyncio.sleep(0)
		return calls_b

	async def fetch_c():
		nonlocal calls_c
		calls_c += 1
		await asyncio.sleep(0)
		return calls_c

	query: KeyedQuery[int] = KeyedQuery(("interval-min",), retries=0, retry_delay=0.01)
	query_computed = Computed(lambda: query, name="test_query(interval-min)")

	obs_a = KeyedQueryResult(
		query_computed,
		fetch_fn=fetch_a,
		refetch_interval=0.02,
		fetch_on_mount=False,
	)
	assert await wait_for(lambda: calls_a >= 1, timeout=0.3)

	obs_b = KeyedQueryResult(
		query_computed,
		fetch_fn=fetch_b,
		refetch_interval=0.01,
		fetch_on_mount=False,
	)
	assert await wait_for(lambda: calls_b >= 1, timeout=0.3)

	calls_a_at = calls_a
	calls_b_at = calls_b
	assert await wait_for(lambda: calls_b >= calls_b_at + 3, timeout=0.3)
	assert calls_a == calls_a_at

	obs_c = KeyedQueryResult(
		query_computed,
		fetch_fn=fetch_c,
		refetch_interval=0.01,
		fetch_on_mount=False,
	)
	assert await wait_for(lambda: calls_c >= 1, timeout=0.3)

	calls_b_at = calls_b
	calls_c_at = calls_c
	assert await wait_for(lambda: calls_c >= calls_c_at + 3, timeout=0.3)
	assert calls_b == calls_b_at

	obs_c.dispose()

	calls_b_at = calls_b
	assert await wait_for(lambda: calls_b >= calls_b_at + 3, timeout=0.3)

	obs_b.dispose()

	calls_a_at = calls_a
	assert await wait_for(lambda: calls_a >= calls_a_at + 2, timeout=0.3)

	obs_a.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_keyed_query_uses_latest_fetch_fn_after_state_recreation():
	"""
	Regression test for bug where keyed query uses stale fetch function after
	state is recreated (e.g., when navigating away and back to a route).

	Scenario:
	1. Create state1 with user_id=1, fetch for key ("user", 1)
	2. Change user_id to 3, fetch for key ("user", 3)
	3. Dispose state1's query (simulate navigating away from route)
	4. Create state2 with user_id=1 (new state, like navigating back)
	5. Refetch for key ("user", 1) - should use state2's fetch_fn, not state1's
	6. Change user_id to 2
	7. Fetch for key ("user", 2) - should use state2's fetch_fn and return user_id=2

	The bug: cached query keeps using old fetch_fn bound to disposed state1,
	which may return wrong data.
	"""
	fetch_log: list[tuple[str, int]] = []

	class QueryState(ps.State):
		user_id: int = 1
		_name: str

		def __init__(self, name: str):
			self._name = name

		@ps.query(retries=0, keep_previous_data=False, gc_time=10, stale_time=0)
		async def user(self) -> dict[str, Any]:
			fetch_log.append((self._name, self.user_id))
			await asyncio.sleep(0)
			return {"id": self.user_id, "name": f"User {self.user_id}"}

		@user.key
		def _user_key(self):
			return ("user", self.user_id)

	# Step 1: Create first state instance
	state1 = QueryState("state1")
	q1 = state1.user

	# Step 2: Fetch for user_id=1
	await q1.wait()
	assert q1.data == {"id": 1, "name": "User 1"}
	assert fetch_log == [("state1", 1)]

	# Step 3: Change to user_id=3 and fetch
	state1.user_id = 3
	await q1.wait()
	assert q1.data == {"id": 3, "name": "User 3"}
	assert fetch_log == [("state1", 1), ("state1", 3)]

	# Step 4: Dispose state1's query (simulate navigating away from route)
	# The query cache still holds the cached queries with gc_time=10
	query_result(q1).dispose()

	# Step 5: Create new state instance (simulate navigating back to route)
	state2 = QueryState("state2")
	q2 = state2.user

	# Step 6: Fetch for user_id=1 (default) - query for ("user", 1) is cached
	# Since stale_time=0, it should refetch
	await q2.wait()
	# The query for ("user", 1) should refetch using state2's fetch_fn
	# Bug: it uses state1's old fetch_fn
	assert q2.data == {"id": 1, "name": "User 1"}, (
		f"Expected data for user_id=1, but got {q2.data}. "
		f"Query may be using stale data!"
	)
	# Verify that state2's fetch was used (not state1's stale function)
	assert fetch_log[-1] == ("state2", 1), (
		f"Expected fetch from state2, but got {fetch_log[-1]}. "
		f"Query is using stale fetch_fn from state1!"
	)

	# Step 7: Change to user_id=2 and fetch
	state2.user_id = 2
	await q2.wait()
	assert q2.data == {"id": 2, "name": "User 2"}, (
		f"Expected data for user_id=2, but got {q2.data}. "
		f"Query may be using stale data or stale fetch_fn!"
	)
	# Verify that state2's fetch was used
	assert fetch_log[-1] == ("state2", 2), (
		f"Expected fetch from state2 with user_id=2, but got {fetch_log[-1]}. "
		f"Query is using stale fetch_fn!"
	)


@pytest.mark.asyncio
@with_render_session
async def test_keyed_query_multiple_observers_use_own_fetch_fn():
	"""
	Test that when multiple state instances share the same query key but have
	different non-key properties, each observer uses its own fetch function.

	Scenario:
	- Two state instances share key ("shared",) but have different `suffix` values
	- The `suffix` property is NOT part of the key
	- When refetch/invalidate is called on each QueryResult, it should use
	  that observer's fetch function with its own `suffix` value
	"""
	fetch_log: list[tuple[str, str]] = []

	class S(ps.State):
		_name: str
		suffix: str  # Not part of the key

		def __init__(self, name: str, suffix: str):
			self._name = name
			self.suffix = suffix

		@ps.query(retries=0, gc_time=10, stale_time=0)
		async def data(self) -> str:
			result = f"{self._name}-{self.suffix}"
			fetch_log.append((self._name, self.suffix))
			await asyncio.sleep(0)
			return result

		@data.key
		def _data_key(self):
			return ("shared",)  # Same key for all instances

	# Create two state instances with different suffix values
	s1 = S("state1", suffix="A")
	s2 = S("state2", suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Initial fetch - q1 fetches first
	await q1.wait()
	assert q1.data == "state1-A"
	assert fetch_log == [("state1", "A")]

	# q2 shares the same query, so it sees the same data
	assert q2.data == "state1-A"

	# Now refetch via q2 - should use s2's fetch function with suffix="B"
	await q2.refetch()
	assert q2.data == "state2-B"
	assert fetch_log[-1] == ("state2", "B"), (
		f"Expected fetch from state2 with suffix=B, but got {fetch_log[-1]}"
	)

	# q1 also sees the updated data (shared query)
	assert q1.data == "state2-B"

	# Refetch via q1 - should use s1's fetch function with suffix="A"
	await q1.refetch()
	assert q1.data == "state1-A"
	assert fetch_log[-1] == ("state1", "A"), (
		f"Expected fetch from state1 with suffix=A, but got {fetch_log[-1]}"
	)

	# Both see the same data
	assert q2.data == "state1-A"

	# Test invalidate() - should also use the correct fetch function
	fetch_log.clear()
	q2.invalidate()
	await q2.wait()
	assert fetch_log[-1] == ("state2", "B"), (
		f"Expected invalidate to use state2's fetch function, but got {fetch_log[-1]}"
	)


@pytest.mark.asyncio
@with_render_session
async def test_keyed_query_wait_after_invalidate_uses_correct_fetch_fn():
	"""
	Test that wait() after invalidate() uses the correct fetch function.
	"""
	fetch_log: list[tuple[str, int]] = []

	class S(ps.State):
		_name: str
		value: int  # Not part of the key

		def __init__(self, name: str, value: int):
			self._name = name
			self.value = value

		@ps.query(retries=0, gc_time=10, stale_time=0)
		async def data(self) -> dict[str, Any]:
			fetch_log.append((self._name, self.value))
			await asyncio.sleep(0)
			return {"source": self._name, "value": self.value}

		@data.key
		def _data_key(self):
			return ("wait-test",)

	s1 = S("state1", value=100)
	s2 = S("state2", value=200)

	q1 = s1.data
	q2 = s2.data

	# wait() on q1 should use s1's fetch function
	await q1.wait()
	assert q1.data == {"source": "state1", "value": 100}
	assert fetch_log == [("state1", 100)]

	# q2 shares the query, sees same data
	assert q2.data == {"source": "state1", "value": 100}

	# Invalidate via q2 and then wait - should use s2's fetch function
	q2.invalidate()
	await q2.wait()
	assert q2.data == {"source": "state2", "value": 200}
	assert fetch_log[-1] == ("state2", 200), (
		f"Expected wait() after invalidate to use state2's fetch function, but got {fetch_log[-1]}"
	)

	# q1 also sees updated data (shared query)
	assert q1.data == {"source": "state2", "value": 200}


@pytest.mark.asyncio
@with_render_session
async def test_unkeyed_query_refetch_uses_own_fetch_fn():
	"""
	Test that unkeyed queries with different state instances use their own
	fetch function when refetching.

	For unkeyed queries, each State instance has its own Query. This test
	verifies that refetch() uses the correct fetch function for each instance,
	even when the divergent property is read inside `with Untrack()`.
	"""
	fetch_log: list[tuple[str, str]] = []

	class S(ps.State):
		_name: str
		tracked_id: int = 1  # This IS tracked (affects when query refetches)
		suffix: str  # Not tracked - read in Untrack context

		def __init__(self, name: str, suffix: str):
			self._name = name
			self.suffix = suffix

		@ps.query(retries=0)
		async def data(self) -> str:
			# tracked_id is tracked (affects key/staleness)
			tid = self.tracked_id
			# suffix is NOT tracked - read in Untrack context
			with Untrack():
				sfx = self.suffix
			result = f"{self._name}-{tid}-{sfx}"
			fetch_log.append((self._name, sfx))
			await asyncio.sleep(0)
			return result

	# Create two state instances with same tracked_id but different suffix
	s1 = S("state1", suffix="X")
	s2 = S("state2", suffix="Y")

	q1 = s1.data
	q2 = s2.data

	# Wait for both to complete initial fetch
	await q1.wait()
	await q2.wait()

	# Verify each query fetched with its own fetch function
	assert q1.data == "state1-1-X"
	assert q2.data == "state2-1-Y"

	# Clear log and test refetch
	fetch_log.clear()

	# refetch on q1 should use s1's fetch function
	await q1.refetch()
	assert fetch_log[-1] == ("state1", "X"), (
		f"Expected refetch to use state1's fetch function with suffix=X, got {fetch_log[-1]}"
	)
	assert q1.data == "state1-1-X"

	# refetch on q2 should use s2's fetch function
	await q2.refetch()
	assert fetch_log[-1] == ("state2", "Y"), (
		f"Expected refetch to use state2's fetch function with suffix=Y, got {fetch_log[-1]}"
	)
	assert q2.data == "state2-1-Y"


@pytest.mark.asyncio
@with_render_session
async def test_unkeyed_query_invalidate_uses_correct_fetch_fn():
	"""
	Test that invalidate() on unkeyed queries uses the correct fetch function
	when the divergent property is read inside `with Untrack()`.

	For unkeyed queries, each State instance has its own Query. This test
	verifies that invalidate() uses the correct fetch function for each instance.
	"""
	fetch_log: list[tuple[str, int]] = []

	class S(ps.State):
		_name: str
		counter: int  # Tracked dependency
		multiplier: int  # Untracked - affects result but not staleness

		def __init__(self, name: str, multiplier: int):
			self._name = name
			self.counter = 0
			self.multiplier = multiplier

		@ps.query(retries=0)
		async def computed(self) -> int:
			c = self.counter  # Tracked
			with Untrack():
				m = self.multiplier  # Untracked
			fetch_log.append((self._name, m))
			await asyncio.sleep(0)
			return c * m

	s1 = S("state1", multiplier=10)
	s2 = S("state2", multiplier=100)

	q1 = s1.computed
	q2 = s2.computed

	# Wait for initial fetches to complete
	await q1.wait()
	await q2.wait()
	assert q1.data == 0  # 0 * 10
	assert q2.data == 0  # 0 * 100

	# Test invalidate uses the correct fetch function
	fetch_log.clear()
	q1.invalidate()
	await q1.wait()
	assert fetch_log[-1] == ("state1", 10), (
		f"Expected invalidate to use state1's fetch function, got {fetch_log[-1]}"
	)
	assert q1.data == 0  # 0 * 10

	q2.invalidate()
	await q2.wait()
	assert fetch_log[-1] == ("state2", 100), (
		f"Expected invalidate to use state2's fetch function, got {fetch_log[-1]}"
	)
	assert q2.data == 0  # 0 * 100

	# Change counter (tracked) and verify refetch uses correct fetch function
	fetch_log.clear()
	s1.counter = 5
	await asyncio.sleep(0)  # Let effect detect change
	await q1.wait()
	assert q1.data == 50  # 5 * 10
	assert fetch_log[-1] == ("state1", 10)

	s2.counter = 5
	await asyncio.sleep(0)
	await q2.wait()
	assert q2.data == 500  # 5 * 100
	assert fetch_log[-1] == ("state2", 100)


@pytest.mark.asyncio
@with_render_session
async def test_keyed_query_concurrent_refetch_cancels_and_uses_new_fetch_fn():
	"""
	Test that when two observers call refetch() concurrently with cancel_refetch=True,
	the second refetch cancels the first and uses its own fetch function.

	Scenario:
	- q1.refetch() starts, its task begins running (awaiting network)
	- q2.refetch() is called while q1's fetch is in progress
	- q2.refetch() should cancel q1's task and start a new one with q2's fetch function
	"""
	fetch_log: list[tuple[str, str, str]] = []  # (name, suffix, status)
	fetch_started = asyncio.Event()
	fetch_can_complete = asyncio.Event()

	class S(ps.State):
		_name: str
		suffix: str

		def __init__(self, name: str, suffix: str):
			self._name = name
			self.suffix = suffix

		@ps.query(retries=0, gc_time=10, stale_time=0)
		async def data(self) -> str:
			fetch_log.append((self._name, self.suffix, "started"))
			fetch_started.set()
			await fetch_can_complete.wait()
			fetch_log.append((self._name, self.suffix, "completed"))
			return f"{self._name}-{self.suffix}"

		@data.key
		def _data_key(self):
			return ("concurrent-test",)

	s1 = S("state1", suffix="A")
	s2 = S("state2", suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Wait for initial fetch to complete
	fetch_can_complete.set()
	await q1.wait()
	fetch_log.clear()
	fetch_started.clear()
	fetch_can_complete.clear()

	# Start q1's refetch (it will block on fetch_can_complete)
	refetch1_task = asyncio.create_task(q1.refetch())
	await fetch_started.wait()  # Wait for q1's fetch to start
	assert fetch_log[-1] == ("state1", "A", "started")

	# Now q2 refetches - should cancel q1's fetch and start its own
	fetch_started.clear()
	refetch2_task = asyncio.create_task(q2.refetch())
	await fetch_started.wait()  # Wait for q2's fetch to start
	assert fetch_log[-1] == ("state2", "B", "started")

	# Let the fetch complete
	fetch_can_complete.set()
	await refetch2_task

	# Verify q2's fetch completed and was used
	assert fetch_log[-1] == ("state2", "B", "completed")
	assert q2.data == "state2-B"

	# q1's refetch task should also complete (it was waiting on the same query)
	await refetch1_task
	# Both see the same data (shared query)
	assert q1.data == "state2-B"


@pytest.mark.asyncio
@with_render_session
async def test_keyed_query_concurrent_refetch_with_cancel_false_deduplicates():
	"""
	Test that when two observers call refetch(cancel_refetch=False) concurrently,
	the second one deduplicates and waits for the first fetch to complete.

	This means the first observer's fetch function is used.
	"""
	fetch_log: list[tuple[str, str]] = []
	fetch_started = asyncio.Event()
	fetch_can_complete = asyncio.Event()

	class S(ps.State):
		_name: str
		suffix: str

		def __init__(self, name: str, suffix: str):
			self._name = name
			self.suffix = suffix

		@ps.query(retries=0, gc_time=10, stale_time=0)
		async def data(self) -> str:
			fetch_log.append((self._name, self.suffix))
			fetch_started.set()
			await fetch_can_complete.wait()
			return f"{self._name}-{self.suffix}"

		@data.key
		def _data_key(self):
			return ("dedup-test",)

	s1 = S("state1", suffix="A")
	s2 = S("state2", suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Wait for initial fetch to complete
	fetch_can_complete.set()
	await q1.wait()
	fetch_log.clear()
	fetch_started.clear()
	fetch_can_complete.clear()

	# Start q1's refetch (it will block on fetch_can_complete)
	refetch1_task = asyncio.create_task(q1.refetch(cancel_refetch=False))
	await fetch_started.wait()
	assert fetch_log == [("state1", "A")]

	# q2 refetches with cancel_refetch=False - should NOT start a new fetch
	# because one is already in progress
	refetch2_task = asyncio.create_task(q2.refetch(cancel_refetch=False))

	# Give it a moment to potentially start (it shouldn't)
	assert not await wait_for(lambda: len(fetch_log) > 1, timeout=0.05)

	# Only one fetch should have happened
	assert len(fetch_log) == 1
	assert fetch_log == [("state1", "A")]

	# Let the fetch complete
	fetch_can_complete.set()
	await refetch1_task
	await refetch2_task

	# Both see the result from s1's fetch function
	assert q1.data == "state1-A"
	assert q2.data == "state1-A"


@pytest.mark.asyncio
@with_render_session
async def test_keyed_query_concurrent_refetch_second_cancels_first_mid_flight():
	"""
	Test that when q2 cancels q1's in-flight fetch, q1's fetch function never completes
	and q2's fetch function is used for the final result.
	"""
	fetch_completion_log: list[str] = []
	fetch_started = asyncio.Event()
	fetch_can_complete = asyncio.Event()

	class S(ps.State):
		_name: str
		suffix: str

		def __init__(self, name: str, suffix: str):
			self._name = name
			self.suffix = suffix

		@ps.query(retries=0, gc_time=10, stale_time=0)
		async def data(self) -> str:
			name = self._name
			fetch_started.set()
			try:
				await fetch_can_complete.wait()
				fetch_completion_log.append(f"{name}-completed")
				return f"{name}-{self.suffix}"
			except asyncio.CancelledError:
				fetch_completion_log.append(f"{name}-cancelled")
				raise

		@data.key
		def _data_key(self):
			return ("cancel-mid-flight",)

	s1 = S("state1", suffix="A")
	s2 = S("state2", suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Wait for initial fetch
	fetch_can_complete.set()
	await q1.wait()
	fetch_completion_log.clear()
	fetch_started.clear()
	fetch_can_complete.clear()

	# Start q1's refetch
	refetch1_task = asyncio.create_task(q1.refetch())
	await fetch_started.wait()

	# q2 cancels q1's fetch and starts its own
	fetch_started.clear()
	refetch2_task = asyncio.create_task(q2.refetch())
	await fetch_started.wait()

	# At this point, q1's fetch should have been cancelled
	await asyncio.sleep(0)  # Let cancellation propagate
	assert "state1-cancelled" in fetch_completion_log

	# Let q2's fetch complete
	fetch_can_complete.set()
	await refetch2_task

	# q2's fetch should complete, q1's should not
	assert "state2-completed" in fetch_completion_log
	assert "state1-completed" not in fetch_completion_log

	# Both see q2's result
	assert q1.data == "state2-B"
	assert q2.data == "state2-B"

	# refetch1_task should complete (it was waiting on the query)
	await refetch1_task


@pytest.mark.asyncio
@with_render_session
async def test_query_result_dispose_cancels_in_flight_fetch():
	"""
	Test that when a QueryResult is disposed while it has an in-flight fetch,
	the fetch is cancelled to avoid running fetch functions from a disposed state.
	"""
	fetch_started = asyncio.Event()
	fetch_completed = asyncio.Event()
	fetch_log: list[str] = []

	class S(ps.State):
		@ps.query(retries=0, gc_time=10)
		async def data(self) -> str:
			fetch_log.append("started")
			fetch_started.set()
			await asyncio.sleep(0.02)  # Long running fetch
			fetch_log.append("completed")
			fetch_completed.set()
			return "result"

		@data.key
		def _key(self):
			return ("dispose-cancel",)

	s = S()
	q = s.data

	# Start fetch but don't wait for it
	wait_task = asyncio.create_task(q.wait())
	await fetch_started.wait()

	# Dispose before fetch completes
	query_result(q).dispose()

	# Give time for cancellation to propagate
	assert await wait_for(
		lambda: wait_task.done() or wait_task.cancelled(), timeout=0.2
	)

	# Fetch should have been cancelled, not completed
	assert "started" in fetch_log
	assert "completed" not in fetch_log

	# The wait task should complete (either with error or cancelled)
	try:
		await asyncio.wait_for(wait_task, timeout=0.02)
	except (asyncio.CancelledError, asyncio.TimeoutError):
		pass  # Expected - task was cancelled


@pytest.mark.asyncio
@with_render_session
async def test_query_result_dispose_does_not_cancel_other_observer_fetch():
	"""
	Test that disposing one observer doesn't cancel a fetch started by another observer.
	"""
	fetch_log: list[tuple[str, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		name: str

		def __init__(self, name: str):
			self.name = name

		@ps.query(retries=0, gc_time=10)
		async def data(self) -> str:
			fetch_log.append((self.name, "started"))
			fetch_started.set()
			await asyncio.sleep(0.01)
			fetch_log.append((self.name, "completed"))
			return f"result-{self.name}"

		@data.key
		def _key(self):
			return ("shared-key",)

	s1 = S("s1")
	s2 = S("s2")

	q1 = s1.data
	q2 = s2.data

	# s1 starts fetch
	wait_task = asyncio.create_task(q1.wait())
	await fetch_started.wait()

	# s2 disposes - should NOT cancel s1's fetch since s1 is the active observer
	query_result(q2).dispose()

	# Wait for s1's fetch to complete
	await wait_task

	# s1's fetch should have completed
	assert ("s1", "started") in fetch_log
	assert ("s1", "completed") in fetch_log


@pytest.mark.asyncio
@with_render_session
async def test_query_result_dispose_reschedules_fetch_from_other_observer():
	"""
	Test that when the initiating observer disposes mid-fetch, the fetch is cancelled
	and rescheduled from another observer if one exists.
	"""
	fetch_log: list[tuple[str, str]] = []
	fetch_started = asyncio.Event()
	first_fetch_cancelled = asyncio.Event()

	class S(ps.State):
		name: str

		def __init__(self, name: str):
			self.name = name

		@ps.query(retries=0, gc_time=10)
		async def data(self) -> str:
			fetch_log.append((self.name, "started"))
			fetch_started.set()
			try:
				await asyncio.sleep(0.01)
				fetch_log.append((self.name, "completed"))
				return f"result-{self.name}"
			except asyncio.CancelledError:
				fetch_log.append((self.name, "cancelled"))
				first_fetch_cancelled.set()
				raise

		@data.key
		def _key(self):
			return ("shared-key",)

	s1 = S("s1")
	s2 = S("s2")

	q1 = s1.data
	q2 = s2.data

	# s1 starts fetch
	wait_task_s1 = asyncio.create_task(q1.wait())
	await fetch_started.wait()
	fetch_started.clear()

	# s1 disposes - should cancel fetch and reschedule from s2
	query_result(q1).dispose()

	# Wait for the first fetch to be cancelled
	await first_fetch_cancelled.wait()

	# Wait for the rescheduled fetch (from s2) to start
	await fetch_started.wait()

	# Wait for s2's fetch to complete via q2
	await q2.wait()

	# Verify the flow: s1 started, s1 cancelled, s2 started, s2 completed
	assert ("s1", "started") in fetch_log
	assert ("s1", "cancelled") in fetch_log
	assert ("s1", "completed") not in fetch_log
	assert ("s2", "started") in fetch_log
	assert ("s2", "completed") in fetch_log

	# s1's wait task should have been cancelled
	try:
		await asyncio.wait_for(wait_task_s1, timeout=0.02)
	except (asyncio.CancelledError, asyncio.TimeoutError):
		pass  # Expected

	# Clean up
	query_result(q2).dispose()


@pytest.mark.asyncio
@with_render_session
async def test_query_result_dispose_no_reschedule_when_no_other_observers():
	"""
	Test that when the only observer disposes mid-fetch, the fetch is cancelled
	and no reschedule happens (since there are no other observers).
	"""
	fetch_log: list[str] = []
	fetch_started = asyncio.Event()
	fetch_cancelled = asyncio.Event()

	class S(ps.State):
		@ps.query(retries=0, gc_time=10)
		async def data(self) -> str:
			fetch_log.append("started")
			fetch_started.set()
			try:
				await asyncio.sleep(0.01)
				fetch_log.append("completed")
				return "result"
			except asyncio.CancelledError:
				fetch_log.append("cancelled")
				fetch_cancelled.set()
				raise

		@data.key
		def _key(self):
			return ("single-observer-key",)

	s = S()
	q = s.data

	# Start fetch
	wait_task = asyncio.create_task(q.wait())
	await fetch_started.wait()

	# Dispose the only observer
	query_result(q).dispose()

	# Wait for cancellation to propagate
	await asyncio.wait_for(fetch_cancelled.wait(), timeout=1.0)

	# Fetch should be cancelled, not completed, and no new fetch started
	assert "started" in fetch_log
	assert "cancelled" in fetch_log
	assert "completed" not in fetch_log
	# Only one "started" entry - no reschedule
	assert fetch_log.count("started") == 1

	# The wait task should complete (cancelled)
	try:
		await asyncio.wait_for(wait_task, timeout=0.02)
	except (asyncio.CancelledError, asyncio.TimeoutError):
		pass  # Expected


@pytest.mark.asyncio
@with_render_session
async def test_key_change_cancels_in_flight_fetch():
	"""
	Test that when a keyed query's key changes, the in-flight fetch for the old key
	is cancelled if this observer was the active observer.

	Scenario: user_id changes from 1 to 2 before the fetch for user_id=1 completes.
	The fetch should be cancelled and not cache data under the wrong key.
	"""
	fetch_log: list[tuple[int, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		user_id: int = 1

		@ps.query(retries=0, gc_time=10)
		async def user(self) -> dict[str, int]:
			uid = self.user_id
			fetch_log.append((uid, "started"))
			fetch_started.set()
			await asyncio.sleep(0.02)  # Long running fetch
			fetch_log.append((uid, "completed"))
			return {"id": uid}

		@user.key
		def _key(self):
			return ("user", self.user_id)

	s = S()
	q = s.user

	# Start fetch for user_id=1
	wait_task = asyncio.create_task(q.wait())
	await fetch_started.wait()
	fetch_started.clear()

	# Change key before fetch completes
	s.user_id = 2
	# Allow the reactive system to process the key change
	assert await wait_for(fetch_started.is_set, timeout=0.2)

	# The old fetch (for user_id=1) should be cancelled
	assert (1, "started") in fetch_log
	assert (1, "completed") not in fetch_log

	# The wait task might error or complete - it's for the old key
	try:
		await asyncio.wait_for(wait_task, timeout=0.02)
	except (asyncio.CancelledError, asyncio.TimeoutError):
		pass  # Expected

	# Clean up
	query_result(q).dispose()


@pytest.mark.asyncio
@with_render_session
async def test_key_change_starts_new_fetch():
	"""
	Test that when a keyed query's key changes, a new fetch is started for the new key.
	"""
	fetch_log: list[tuple[int, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		user_id: int = 1

		@ps.query(retries=0, gc_time=10)
		async def user(self) -> dict[str, int]:
			uid = self.user_id
			fetch_log.append((uid, "started"))
			fetch_started.set()
			await asyncio.sleep(0.01)
			fetch_log.append((uid, "completed"))
			return {"id": uid}

		@user.key
		def _key(self):
			return ("user", self.user_id)

	s = S()
	q = s.user

	# Start fetch for user_id=1
	await fetch_started.wait()
	fetch_started.clear()

	# Change key - should trigger new fetch for user_id=2
	s.user_id = 2
	await fetch_started.wait()

	# Both fetches should have started
	assert (1, "started") in fetch_log
	assert (2, "started") in fetch_log

	# Wait for the new fetch to complete
	await q.wait()

	# New fetch should complete with correct data
	assert (2, "completed") in fetch_log
	assert q.data == {"id": 2}

	# Clean up
	query_result(q).dispose()


@pytest.mark.asyncio
@with_render_session
async def test_key_change_does_not_affect_other_observer():
	"""
	Test that when one observer's key changes, it doesn't affect another observer
	on the same old key that started the fetch.
	"""
	fetch_log: list[tuple[str, int, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		name: str
		user_id: int

		def __init__(self, name: str, user_id: int):
			self.name = name
			self.user_id = user_id

		@ps.query(retries=0, gc_time=10)
		async def user(self) -> dict[str, int]:
			uid = self.user_id
			fetch_log.append((self.name, uid, "started"))
			fetch_started.set()
			await asyncio.sleep(0.02)
			fetch_log.append((self.name, uid, "completed"))
			return {"id": uid}

		@user.key
		def _key(self):
			return ("user", self.user_id)

	# Two states observing the same key initially
	s1 = S("s1", 1)
	s2 = S("s2", 1)

	q1 = s1.user
	q2 = s2.user

	# s1 starts fetch for key ("user", 1)
	wait_task = asyncio.create_task(q1.wait())
	await fetch_started.wait()
	fetch_started.clear()

	# s2 changes its key - but s1 started the fetch, so it should continue
	s2.user_id = 2
	assert await wait_for(fetch_started.is_set, timeout=0.2)

	# Wait for s1's fetch to complete
	await wait_task

	# s1's fetch should complete successfully
	assert ("s1", 1, "started") in fetch_log
	assert ("s1", 1, "completed") in fetch_log
	assert q1.data == {"id": 1}

	# Clean up
	query_result(q1).dispose()
	query_result(q2).dispose()


# --- Protocol Tests ---


@pytest.mark.asyncio
@with_render_session
async def test_query_result_protocol_isinstance_keyed():
	"""KeyedQueryResult instances should be recognized as QueryResult via isinstance."""

	class S(ps.State):
		@ps.query
		async def my_query(self):
			return "data"

		@my_query.key
		def _key(self):
			return ("test",)

	s = S()
	result = s.my_query
	assert isinstance(result, QueryResult)


@pytest.mark.asyncio
@with_render_session
async def test_query_result_protocol_isinstance_unkeyed():
	"""UnkeyedQuery instances should be recognized as QueryResult via isinstance."""

	class S(ps.State):
		@ps.query
		async def my_query(self):
			return "data"

	s = S()
	result = s.my_query
	assert isinstance(result, UnkeyedQueryResult)


# --- List Key Tests ---


@pytest.mark.asyncio
@with_render_session
async def test_query_with_static_list_key():
	"""Test that a static list key works and is normalized to tuple."""

	class S(ps.State):
		@ps.query(key=["users", "current"])
		async def current_user(self):
			return {"name": "Alice"}

	s = S()
	q = s.current_user
	await q.wait()

	assert q.data == {"name": "Alice"}

	# The query should be accessible via both list and tuple keys
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]
	assert store.get(["users", "current"]) is not None
	assert store.get(("users", "current")) is not None
	assert store.get(["users", "current"]) is store.get(("users", "current"))


@pytest.mark.asyncio
@with_render_session
async def test_query_with_dynamic_list_key():
	"""Test that a dynamic list key (from method) works and is normalized to tuple."""

	class S(ps.State):
		user_id: int = 1

		@ps.query
		async def user(self):
			return {"id": self.user_id}

		@user.key
		def _user_key(self) -> ps.QueryKey:
			return ["user", self.user_id]  # List key

	s = S()
	q = s.user
	await q.wait()

	assert q.data == {"id": 1}

	# The query should be accessible via both list and tuple keys
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]
	assert store.get(["user", 1]) is not None
	assert store.get(("user", 1)) is not None
	assert store.get(["user", 1]) is store.get(("user", 1))

	# Change user_id and verify new key works
	s.user_id = 2
	await q.wait()
	assert q.data == {"id": 2}
	assert store.get(["user", 2]) is not None
	assert store.get(("user", 2)) is not None


@pytest.mark.asyncio
@with_render_session
async def test_query_with_callable_list_key_updates_on_inplace_change():
	"""Callable list keys should be normalized so in-place changes update the key."""

	class S(ps.State):
		user_id: int = 1
		key_parts: list[Any]

		def __init__(self):
			self.key_parts = ["user", 1]

		def _key(self) -> ps.QueryKey:
			_ = self.user_id  # ensure reactive dependency
			return self.key_parts

		@ps.query(retries=0, gc_time=10, key=_key)
		async def user(self) -> int:
			return self.user_id

	s = S()
	q = s.user
	await q.wait()
	result = query_result(q)
	assert isinstance(result, KeyedQueryResult)
	assert result._query().key == ("user", 1)  # pyright: ignore[reportPrivateUsage]

	# Mutate list in-place and trigger recompute
	s.key_parts[1] = 2
	s.user_id = 2

	def key_matches() -> bool:
		return result._query().key == ("user", 2)  # pyright: ignore[reportPrivateUsage]

	assert await wait_for(key_matches, timeout=0.2)
