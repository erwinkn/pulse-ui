import asyncio

import pytest
from pulse.queries.query import Query, QueryResult
from pulse.queries.store import QueryStore
from pulse.reactive import Computed


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
	assert entry.fetch_status.read() == "idle"
	assert entry.data.read() is None
	assert entry.error.read() is None

	# Start fetch
	task = asyncio.create_task(entry.refetch())
	# Let it start
	await asyncio.sleep(0)

	# Check sync loading state (AsyncQueryEffect)
	assert entry.status.read() == "loading"
	assert entry.fetch_status.read() == "fetching"

	await task

	assert entry.status.read() == "success"
	assert entry.fetch_status.read() == "idle"
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
	assert entry.fetch_status.read() == "fetching"

	try:
		await task
	except ValueError:
		pass

	assert entry.status.read() == "error"
	assert entry.fetch_status.read() == "idle"
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
	assert res1 == 1
	assert res2 == 1


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
	assert res2 == 2


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

	# Force fetch_status to idle (status is already loading from initial_data=None)
	entry.status.write("success")
	entry.fetch_status.write("idle")

	# Schedule effect (like a dependency change would)
	# We need to manually trigger push_change or run
	entry.effect.push_change()

	# Should be LOADING immediately
	assert entry.status.read() == "success"
	assert entry.fetch_status.read() == "fetching"

	# Run it to clear
	await entry.effect.run()
	assert entry.status.read() == "success"
	assert entry.fetch_status.read() == "idle"


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
