"""
Staleness and suspend/resume semantics for queries (TanStack-style).

- invalidate() marks data stale persistently: an unobserved query refetches
  when it is next observed or when the session resumes.
- Session disconnect pauses interval refetching; reconnect restarts intervals
  and refetches stale queries.
"""

import asyncio
from typing import Any

import pulse as ps
import pytest
from pulse.queries.query import KeyedQueryResult, UnkeyedQueryResult
from pulse.queries.store import QueryStore
from pulse.reactive import Computed
from pulse.render_session import RenderSession
from pulse.routing import RouteTree
from pulse.test_helpers import wait_for


class FetchCounter:
	count: int

	def __init__(self) -> None:
		self.count = 0

	async def fetch(self) -> int:
		self.count += 1
		return self.count


def observe(
	store: QueryStore,
	key: tuple[Any, ...],
	counter: FetchCounter,
	**kwargs: Any,
) -> KeyedQueryResult[int]:
	store.ensure(key)
	return KeyedQueryResult(
		Computed(lambda: store.ensure(key)), fetch_fn=counter.fetch, **kwargs
	)


@pytest.mark.asyncio
async def test_invalidate_persists_without_observers():
	store = QueryStore()
	counter = FetchCounter()
	result = observe(store, ("a",), counter, stale_time=1000.0)
	await wait_for(lambda: counter.count == 1)
	query = store.ensure(("a",))
	result.dispose()
	assert query.observers == []

	# No observers: marks stale, doesn't fetch
	query.invalidate()
	await asyncio.sleep(0.01)
	assert counter.count == 1
	assert query.is_stale(1000.0)

	# Next observer refetches despite fresh-looking last_updated
	result2 = observe(store, ("a",), counter, stale_time=1000.0)
	await wait_for(lambda: counter.count == 2)
	assert not query.is_stale(1000.0)
	result2.dispose()


@pytest.mark.asyncio
async def test_is_stale_clears_after_refetch():
	store = QueryStore()
	counter = FetchCounter()
	result = observe(store, ("a",), counter, stale_time=1000.0)
	await wait_for(lambda: counter.count == 1)
	query = store.ensure(("a",))

	assert not result.is_stale()
	query.invalidate()
	await wait_for(lambda: counter.count == 2)
	assert not result.is_stale()
	result.dispose()


@pytest.mark.asyncio
async def test_suspend_pauses_keyed_interval_refetching():
	store = QueryStore()
	counter = FetchCounter()
	result = observe(store, ("a",), counter, refetch_interval=0.02)
	await wait_for(lambda: counter.count >= 1)

	store.suspend_all()
	await asyncio.sleep(0.01)  # let any in-flight fetch settle
	paused_count = counter.count
	await asyncio.sleep(0.08)
	assert counter.count == paused_count

	# Resume runs an immediate catch-up fetch and restarts the interval
	store.resume_all()
	await wait_for(lambda: counter.count > paused_count)
	result.dispose()


@pytest.mark.asyncio
async def test_resume_refetches_stale_queries():
	store = QueryStore()
	counter = FetchCounter()
	result = observe(store, ("a",), counter, stale_time=0.0)
	await wait_for(lambda: counter.count == 1)

	store.suspend_all()
	store.resume_all()
	await wait_for(lambda: counter.count == 2)
	result.dispose()


@pytest.mark.asyncio
async def test_resume_skips_fresh_queries():
	store = QueryStore()
	counter = FetchCounter()
	result = observe(store, ("a",), counter, stale_time=1000.0)
	await wait_for(lambda: counter.count == 1)

	store.suspend_all()
	store.resume_all()
	await asyncio.sleep(0.02)
	assert counter.count == 1
	result.dispose()


@pytest.mark.asyncio
async def test_unkeyed_suspend_resume_interval():
	store = QueryStore()
	counter = FetchCounter()
	result = UnkeyedQueryResult(
		counter.fetch,
		refetch_interval=0.02,
		on_dispose=store.unregister_unkeyed,
	)
	store.register_unkeyed(result)
	await wait_for(lambda: counter.count >= 1)

	store.suspend_all()
	await asyncio.sleep(0.01)
	paused_count = counter.count
	await asyncio.sleep(0.08)
	assert counter.count == paused_count

	store.resume_all()
	await wait_for(lambda: counter.count > paused_count)

	result.dispose()
	assert result not in store._unkeyed  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_unkeyed_resume_refetches_stale():
	counter = FetchCounter()
	result = UnkeyedQueryResult(counter.fetch, stale_time=0.0)
	await wait_for(lambda: counter.count == 1)

	result.suspend()
	result.resume()
	await wait_for(lambda: counter.count == 2)

	fresh_counter = FetchCounter()
	fresh = UnkeyedQueryResult(fresh_counter.fetch, stale_time=1000.0)
	await wait_for(lambda: fresh_counter.count == 1)
	fresh.suspend()
	fresh.resume()
	await asyncio.sleep(0.02)
	assert fresh_counter.count == 1

	result.dispose()
	fresh.dispose()


@pytest.mark.asyncio
async def test_infinite_invalidate_marks_stale_without_observers():
	store = QueryStore()
	query = store.ensure_infinite(
		("inf",), initial_page_param=0, get_next_page_param=lambda pages: None
	)
	assert not query.is_stale(1000.0) or query.last_updated.value == 0.0
	query.invalidate()
	assert query.is_stale(1000.0)


@pytest.mark.asyncio
async def test_infinite_resume_does_not_stack_fetch_on_inflight():
	"""Resume during an in-flight infinite fetch must not enqueue a duplicate."""
	from pulse.queries.infinite_query import InfiniteQuery, InfiniteQueryResult

	calls = 0
	release = asyncio.Event()

	async def fetcher(page_param: int) -> int:
		nonlocal calls
		calls += 1
		await release.wait()
		return page_param

	query: InfiniteQuery[int, int] = InfiniteQuery(
		("inf", "inflight"),
		initial_page_param=0,
		get_next_page_param=lambda _pages: None,
	)
	observer = InfiniteQueryResult(
		Computed(lambda: query, name="inf(inflight)"),
		fetch_fn=fetcher,
		stale_time=0.0,
	)
	# Initial fetch is now in flight (blocked on `release`)
	await wait_for(lambda: calls == 1)

	# Disconnect + reconnect while the fetch is still running
	query.suspend()
	query.resume()
	await asyncio.sleep(0.01)

	# No second fetch was stacked behind the in-flight one
	assert calls == 1

	release.set()
	await query.wait()
	assert calls == 1

	observer.dispose()
	query.dispose()


@pytest.mark.asyncio
async def test_infinite_interval_resume_does_not_stack_fetch_on_inflight():
	"""Resume of an interval infinite query must not stack a fetch via the
	recreated interval effect's immediate catch-up tick."""
	from pulse.queries.infinite_query import InfiniteQuery, InfiniteQueryResult

	calls = 0
	release = asyncio.Event()

	async def fetcher(page_param: int) -> int:
		nonlocal calls
		calls += 1
		await release.wait()
		return page_param

	query: InfiniteQuery[int, int] = InfiniteQuery(
		("inf", "interval-inflight"),
		initial_page_param=0,
		get_next_page_param=lambda _pages: None,
	)
	# Long interval so only the resume-time immediate tick matters in-window
	observer = InfiniteQueryResult(
		Computed(lambda: query, name="inf(interval-inflight)"),
		fetch_fn=fetcher,
		refetch_interval=100.0,
	)
	await wait_for(lambda: calls == 1)

	query.suspend()
	query.resume()  # recreates the interval effect (immediate tick)
	await asyncio.sleep(0.01)

	assert calls == 1  # the immediate tick saw work in flight and skipped

	release.set()
	await query.wait()
	assert calls == 1

	observer.dispose()
	query.dispose()


@pytest.mark.asyncio
async def test_session_connection_drives_query_suspension():
	session = RenderSession("test-id", RouteTree([]))
	store = session.query_store
	counter = FetchCounter()
	result = observe(store, ("a",), counter, stale_time=0.0)
	await wait_for(lambda: counter.count == 1)

	# First connect is not a resume: no refetch
	session.connect(lambda msg: None)
	await asyncio.sleep(0.02)
	assert counter.count == 1
	assert store.suspended is False

	session.disconnect()
	assert store.suspended is True

	# Reconnect refetches the stale query
	with ps.PulseContext.update(render=session):
		session.connect(lambda msg: None)
	assert store.suspended is False
	await wait_for(lambda: counter.count == 2)

	result.dispose()
	session.close()
