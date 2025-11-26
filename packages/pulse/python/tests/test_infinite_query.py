import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import pulse as ps
import pytest
from pulse.queries.common import ActionError
from pulse.queries.infinite_query import Page
from pulse.render_session import RenderSession
from pulse.routing import RouteTree


class ProjectsPage(TypedDict):
	items: list[int]
	next: int | None


class RefetchPage(TypedDict):
	page: int
	next: int | None


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	"""Set up a PulseContext with an App for all tests."""
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def with_render_session(fn: Callable[..., Awaitable[object]]):
	"""Decorator to wrap test functions with a RenderSession context."""

	async def wrapper(*args: Any, **kwargs: Any) -> object:
		routes = RouteTree([])
		session = RenderSession("test-session", routes)
		with ps.PulseContext.update(render=session):
			return await fn(*args, **kwargs)

	return wrapper


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_fetch_next_pages():
	class S(ps.State):
		calls: int = 0

		@ps.infinite_query(initial_page_param=0, retries=0)
		async def projects(self, page_param: int) -> ProjectsPage:
			self.calls += 1
			await asyncio.sleep(0)
			next_val = page_param + 1 if page_param < 2 else None
			return {"items": [page_param], "next": next_val}

		@projects.get_next_page_param
		def _get_next(self, pages: list[Page[ProjectsPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@projects.key
		def _key(self):
			return ("projects",)

	s = S()
	q = s.projects

	await q.wait()
	assert q.pages == [{"items": [0], "next": 1}]
	assert q.has_next_page is True

	await q.fetch_next_page()
	assert q.pages is not None
	assert [p["items"][0] for p in q.pages] == [0, 1]
	assert q.has_next_page is True

	await q.fetch_next_page()
	assert q.pages is not None
	assert [p["items"][0] for p in q.pages] == [0, 1, 2]
	assert q.has_next_page is False
	assert s.calls == 3


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_max_pages_trims_forward():
	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, max_pages=2, retries=0)
		async def nums(self, page_param: int) -> int:
			await asyncio.sleep(0)
			return page_param

		@nums.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 3 else None

		@nums.key
		def _key(self):
			return ("nums",)

	s = S()
	q = s.nums

	await q.wait()
	await q.fetch_next_page()
	await q.fetch_next_page()

	assert q.pages == [1, 2]
	assert q.page_params == [1, 2]
	assert q.has_next_page is True

	await q.fetch_next_page()
	assert q.pages == [2, 3]
	assert q.page_params == [2, 3]
	assert q.has_next_page is False


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_fetch_previous_pages():
	class S(ps.State):
		@ps.infinite_query(initial_page_param=1, retries=0)
		async def nums(self, page_param: int) -> int:
			await asyncio.sleep(0)
			return page_param

		@nums.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 2 else None

		@nums.get_previous_page_param
		def _get_prev(self, pages: list[Page[int, int]]) -> int | None:
			return pages[0].param - 1 if pages[0].param > 0 else None

		@nums.key
		def _key(self):
			return ("nums-prev",)

	s = S()
	q = s.nums

	await q.wait()
	assert q.pages == [1]
	assert q.has_previous_page is True

	await q.fetch_previous_page()
	assert q.pages == [0, 1]
	assert q.has_previous_page is False

	await q.fetch_next_page()
	assert q.pages == [0, 1, 2]
	assert q.has_next_page is False


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_page_error_sets_error():
	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, retries=0)
		async def sometimes_fail(self, page_param: int) -> int:
			await asyncio.sleep(0)
			if page_param == 1:
				raise RuntimeError("boom")
			return page_param

		@sometimes_fail.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int:
			return pages[-1].param + 1

		@sometimes_fail.key
		def _key(self):
			return ("fail-page",)

	s = S()
	q = s.sometimes_fail

	await q.wait()
	assert q.pages == [0]

	# TanStack style: fetch_next_page returns ActionResult
	result = await q.fetch_next_page()
	assert result.status == "error"
	assert isinstance(result, ActionError)
	assert isinstance(result.error, RuntimeError)

	assert q.is_error is True
	assert q.pages == [0]
	assert q.is_fetching_next_page is False


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_page_param_decorators():
	class S(ps.State):
		@ps.infinite_query(initial_page_param=1)
		async def nums(self, page_param: int):
			await asyncio.sleep(0)
			return page_param

		@nums.get_next_page_param
		def _next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 2 else None

		@nums.get_previous_page_param
		def _prev(self, pages: list[Page[int, int]]) -> int | None:
			return pages[0].param - 1 if pages[0].param > 0 else None

		@nums.key
		def _key(self):
			return ("decorator-params",)

	s = S()
	q = s.nums

	await q.wait()
	assert q.pages == [1]
	assert q.has_next_page is True
	assert q.has_previous_page is True

	await q.fetch_next_page()
	assert q.pages == [1, 2]
	assert q.has_previous_page is True

	await q.fetch_previous_page()
	assert q.pages == [0, 1, 2]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_refetches_all_pages_sequentially():
	class S(ps.State):
		called: list[int] = []

		@ps.infinite_query(initial_page_param=0, stale_time=5)
		async def nums(self, page_param: int) -> RefetchPage:
			self.called.append(page_param)
			await asyncio.sleep(0)
			return {
				"page": page_param,
				"next": page_param + 1 if page_param < 3 else None,
			}

		@nums.get_next_page_param
		def _next(self, pages: list[Page[RefetchPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@nums.key
		def _key(self):
			return ("refetch-reset",)

	s = S()
	q = s.nums

	await q.wait()
	await q.fetch_next_page()
	await q.fetch_next_page()
	assert q.pages is not None
	assert [p["page"] for p in q.pages] == [0, 1, 2]
	assert s.called == [0, 1, 2]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_recomputes_next_params():
	class S(ps.State):
		stop_after_first: bool = False

		@ps.infinite_query(initial_page_param=0)
		async def nums(self, page_param: int) -> RefetchPage:
			await asyncio.sleep(0)
			next_val = (
				None
				if self.stop_after_first and page_param == 0
				else (page_param + 1 if page_param < 2 else None)
			)
			return {"page": page_param, "next": next_val}

		@nums.get_next_page_param
		def _next(self, pages: list[Page[RefetchPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@nums.key
		def _key(self):
			return ("refetch-recompute",)

	s = S()
	q = s.nums

	await q.wait()
	await q.fetch_next_page()
	await q.fetch_next_page()
	assert q.pages is not None
	assert [p["page"] for p in q.pages] == [0, 1, 2]

	s.stop_after_first = True
	await q.refetch()
	assert q.pages is not None
	assert [p["page"] for p in q.pages] == [0]
	assert q.has_next_page is False


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_page_filter():
	class VersionedPage(TypedDict):
		page: int
		next: int | None
		version: int

	class S(ps.State):
		versions: dict[int, int] = {0: 0, 1: 0}

		@ps.infinite_query(initial_page_param=0)
		async def nums(self, page_param: int) -> VersionedPage:
			await asyncio.sleep(0)
			return {
				"page": page_param,
				"next": page_param + 1 if page_param < 1 else None,
				"version": self.versions[page_param],
			}

		@nums.get_next_page_param
		def _next(self, pages: list[Page[VersionedPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@nums.key
		def _key(self):
			return ("refetch-filter",)

	s = S()
	q = s.nums

	await q.wait()
	await q.fetch_next_page()
	assert q.pages is not None
	assert [p["page"] for p in q.pages] == [0, 1]
	assert [p["version"] for p in q.pages] == [0, 0]

	s.versions[0] = 1
	s.versions[1] = 2

	await q.refetch(refetch_page=lambda page, idx, all_pages: idx == 0)
	assert q.pages is not None
	print("PAges:", q.pages)
	assert [p["version"] for p in q.pages] == [1, 0]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_set_initial_data_api_and_cache_helpers():
	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, stale_time=5)
		async def nums(self, page_param: int) -> RefetchPage:
			await asyncio.sleep(0)
			return {"page": page_param, "next": None}

		@nums.get_next_page_param
		def _next(self, pages: list[Page[RefetchPage, int]]) -> int | None:
			return None

		@nums.key
		def _key(self):
			return ("inf-set-initial",)

	s = S()
	q = s.nums

	# Seed cache before fetch
	q.set_initial_data(pages=[Page({"page": 99, "next": None}, 0)], updated_at=0)
	assert q.pages == [{"page": 99, "next": None}]
	assert q.is_stale() is True

	# Fetch will overwrite with real data
	await q.wait()
	assert q.pages == [{"page": 0, "next": None}]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_set_initial_data_no_effect_after_load():
	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, stale_time=5)
		async def nums(self, page_param: int) -> RefetchPage:
			await asyncio.sleep(0)
			return {"page": page_param, "next": None}

		@nums.get_next_page_param
		def _next(self, pages: list[Page[RefetchPage, int]]) -> int | None:
			return None

		@nums.key
		def _key(self):
			return ("inf-no-effect-after-load",)

	s = S()
	q = s.nums

	# Complete first fetch
	await q.wait()
	assert q.pages == [{"page": 0, "next": None}]
	assert q.status == "success"

	# Try to set initial data after query has loaded - should have no effect
	old_pages = q.pages
	q.set_initial_data(pages=[Page({"page": 999, "next": None}, 0)], updated_at=0)
	assert q.pages == old_pages  # Data should not change
	assert q.pages == [{"page": 0, "next": None}]  # Should still be the fetched data


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_fetch_page_basic():
	"""Test that fetch_page refetches an existing page."""
	fetch_count = 0

	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, max_pages=3, retries=0)
		async def nums(self, page_param: int) -> int:
			nonlocal fetch_count
			fetch_count += 1
			await asyncio.sleep(0)
			return page_param * 10 + fetch_count  # Different value each fetch

		@nums.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 10 else None

		@nums.key
		def _key(self):
			return ("fetch-page-basic",)

	s = S()
	q = s.nums

	# Initial fetch
	await q.wait()
	assert q.pages == [1]  # 0*10 + 1
	assert q.page_params == [0]

	# Fetch next page
	await q.fetch_next_page()
	assert q.pages == [1, 12]  # [0*10+1, 1*10+2]
	assert q.page_params == [0, 1]

	# Fetch non-existent page returns ActionSuccess with None data
	result = await q.fetch_page(5)
	assert result.status == "success"
	assert result.data is None
	assert q.pages == [1, 12]  # Unchanged

	# Refetch existing page 0 updates it
	result = await q.fetch_page(0)
	assert result.status == "success"
	assert result.data == 3  # 0*10 + 3
	assert q.pages == [3, 12]
	assert q.page_params == [0, 1]

	# Refetch existing page 1 updates it
	result = await q.fetch_page(1)
	assert result.status == "success"
	assert result.data == 14  # 1*10 + 4
	assert q.pages == [3, 14]
	assert q.page_params == [0, 1]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_retry_on_initial_fetch():
	"""Test that infinite query retries on initial fetch failure."""

	class S(ps.State):
		attempts: int = 0

		@ps.infinite_query(initial_page_param=0, retries=2, retry_delay=0.01)
		async def failing_query(self, page_param: int) -> int:
			self.attempts += 1
			if self.attempts < 3:  # Fail first 2 attempts
				raise ValueError(f"attempt {self.attempts}")
			return page_param

		@failing_query.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None

		@failing_query.key
		def _key(self):
			return ("retry-initial",)

	s = S()
	q = s.failing_query

	await q.wait()
	assert q.status == "success"
	assert q.pages == [0]
	assert s.attempts == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_retry_on_fetch_page():
	"""Test that fetch_page retries on failure when refetching existing page."""

	class S(ps.State):
		attempts: int = 0

		@ps.infinite_query(initial_page_param=0, retries=2, retry_delay=0.01)
		async def failing_query(self, page_param: int) -> int:
			self.attempts += 1
			# Fail attempts 2 and 3 (when refetching page 0)
			if self.attempts in (2, 3):
				raise ValueError(f"attempt {self.attempts}")
			return page_param * 10 + self.attempts

		@failing_query.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 2 else None

		@failing_query.key
		def _key(self):
			return ("retry-fetch-page",)

	s = S()
	q = s.failing_query

	# Initial fetch should succeed (attempt 1)
	await q.wait()
	assert q.pages == [1]  # 0*10 + 1
	assert s.attempts == 1

	# Refetch page 0 should retry and succeed on attempt 4
	result = await q.fetch_page(0)
	assert result.status == "success"
	assert result.data == 4  # 0*10 + 4
	assert q.pages == [4]
	assert s.attempts == 4  # 1 initial + 3 for refetch (2 failed, 1 success)


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_retry_exhausted():
	"""Test that infinite query fails after retries are exhausted."""

	class S(ps.State):
		attempts: int = 0

		@ps.infinite_query(initial_page_param=0, retries=1, retry_delay=0.01)
		async def failing_query(self, page_param: int) -> int:
			self.attempts += 1
			raise ValueError(f"attempt {self.attempts}")

		@failing_query.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None

		@failing_query.key
		def _key(self):
			return ("retry-exhausted",)

	s = S()
	q = s.failing_query

	await q.wait()
	assert q.status == "error"
	assert q.error is not None
	assert isinstance(q.error, ValueError)
	assert q.error.args[0] == "attempt 2"  # 1 initial + 1 retry
	assert s.attempts == 2


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_interval():
	"""Test that refetch_interval triggers automatic refetches."""

	class S(ps.State):
		calls: int = 0

		@ps.infinite_query(initial_page_param=0, retries=0, refetch_interval=0.05)
		async def items(self, page_param: int) -> int:
			self.calls += 1
			await asyncio.sleep(0)
			return self.calls

		@items.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None  # Single page

		@items.key
		def _key(self):
			return ("interval-items",)

	s = S()
	q = s.items

	# Initial fetch
	await q.wait()
	assert s.calls == 1
	assert q.pages == [1]

	# Wait for interval to trigger refetch
	await asyncio.sleep(0.08)
	assert s.calls == 2
	assert q.pages == [2]

	# Wait for another interval
	await asyncio.sleep(0.06)
	assert s.calls == 3
	assert q.pages == [3]

	q.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_interval_stops_on_dispose():
	"""Test that refetch_interval stops when query is disposed."""

	class S(ps.State):
		calls: int = 0

		@ps.infinite_query(initial_page_param=0, retries=0, refetch_interval=0.05)
		async def items(self, page_param: int) -> int:
			self.calls += 1
			await asyncio.sleep(0)
			return self.calls

		@items.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None

		@items.key
		def _key(self):
			return ("interval-dispose",)

	s = S()
	q = s.items

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
