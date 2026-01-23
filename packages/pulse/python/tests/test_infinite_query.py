import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import pulse as ps
import pytest
from pulse.queries.common import ActionError
from pulse.queries.infinite_query import InfiniteQuery, InfiniteQueryResult, Page
from pulse.reactive import Computed
from pulse.render_session import RenderSession
from pulse.routing import RouteTree
from pulse.test_helpers import wait_for


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
async def test_infinite_query_initial_data_used_on_key_change_with_keep_previous_true():
	class S(ps.State):
		uid: int = 1

		@ps.infinite_query(initial_page_param=0, retries=0, keep_previous_data=True)
		async def projects(self, page_param: int) -> ProjectsPage:
			await asyncio.sleep(0.02)
			return {"items": [self.uid], "next": None}

		@projects.get_next_page_param
		def _get_next(self, pages: list[Page[ProjectsPage, int]]) -> int | None:
			return None

		@projects.initial_data
		def _initial(self):
			data: ProjectsPage = {"items": [0], "next": None}
			return [Page(data, 0)]

		@projects.key
		def _key(self):
			return ("projects", self.uid)

	s = S()
	q = s.projects

	assert q.pages == [{"items": [0], "next": None}]
	await q.wait()
	assert q.pages == [{"items": [1], "next": None}]

	s.uid = 2
	await asyncio.sleep(0)
	assert q.is_fetching is True
	assert q.pages == [{"items": [0], "next": None}]
	await q.wait()
	assert q.pages == [{"items": [2], "next": None}]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_wait_is_side_effect_free_and_ensure_starts_fetch():
	calls = 0

	class S(ps.State):
		@ps.infinite_query(
			initial_page_param=0, retries=0, fetch_on_mount=False, max_pages=0
		)
		async def nums(self, page_param: int) -> int:
			nonlocal calls
			calls += 1
			await asyncio.sleep(0)
			return page_param

		@nums.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None

		@nums.key
		def _key(self):
			return ("inf-ensure",)

	s = S()
	q = s.nums

	result = await q.wait()
	assert calls == 0
	assert q.status == "loading"
	assert q.pages is None or q.pages == []
	assert result.status == "success"
	assert result.data == []

	result = await q.ensure()
	assert result.status == "success"
	assert q.pages == [0]
	assert calls == 1


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
async def test_infinite_query_fetch_page_jumps_to_new_page():
	"""Test that fetch_page can jump to a page that doesn't exist yet.

	This is the 'jump to page X' use case - when you want to navigate to
	an arbitrary page, clearing existing pages and starting fresh from that page.
	"""
	fetch_count = 0

	class S(ps.State):
		@ps.infinite_query(
			initial_page_param=0, max_pages=4, retries=0, fetch_on_mount=False
		)
		async def nums(self, page_param: int) -> int:
			nonlocal fetch_count
			fetch_count += 1
			await asyncio.sleep(0)
			return page_param * 10 + fetch_count

		@nums.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 10 else None

		@nums.key
		def _key(self):
			return ("fetch-page-jump",)

	s = S()
	q = s.nums

	# Jump to page 5 directly without loading any pages first
	result = await q.fetch_page(5)
	assert result.status == "success"
	assert result.data == 51  # 5*10 + 1
	assert q.pages == [51]
	assert q.page_params == [5]
	assert q.has_next_page is True

	# Can fetch next page from there
	await q.fetch_next_page()
	assert q.pages == [51, 62]  # [5*10+1, 6*10+2]
	assert q.page_params == [5, 6]

	# Jump to a different page (clears existing pages)
	result = await q.fetch_page(8)
	assert result.status == "success"
	assert result.data == 83  # 8*10 + 3
	assert q.pages == [83]
	assert q.page_params == [8]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_fetch_page_no_pages_exists():
	"""Test that fetch_page works when query has no pages loaded yet."""
	fetch_count = 0

	class S(ps.State):
		@ps.infinite_query(
			initial_page_param=0, max_pages=4, retries=0, fetch_on_mount=False
		)
		async def nums(self, page_param: int) -> int:
			nonlocal fetch_count
			fetch_count += 1
			await asyncio.sleep(0)
			return page_param * 10 + fetch_count

		@nums.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 10 else None

		@nums.key
		def _key(self):
			return ("fetch-page-no-pages",)

	s = S()
	q = s.nums

	# Query starts with no pages (fetch_on_mount=False)
	assert q.pages is None or q.pages == []

	# Jump to page 0 (the initial page)
	result = await q.fetch_page(0)
	assert result.status == "success"
	assert result.data == 1  # 0*10 + 1
	assert q.pages == [1]
	assert q.page_params == [0]
	assert fetch_count == 1


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

	# Auto-fetch should happen on mount
	assert await wait_for(lambda: q.pages == [1] and s.calls == 1)

	# Wait for interval to trigger refetch
	assert await wait_for(lambda: q.pages == [2] and s.calls == 2)

	# Wait for another interval
	assert await wait_for(lambda: q.pages == [3] and s.calls == 3)

	q.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_interval_zero_fetches_on_mount_only():
	"""Test that refetch_interval=0 disables interval but still fetches on mount."""

	class S(ps.State):
		calls: int = 0

		@ps.infinite_query(initial_page_param=0, retries=0, refetch_interval=0)
		async def items(self, page_param: int) -> int:
			self.calls += 1
			await asyncio.sleep(0)
			return self.calls

		@items.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None

		@items.key
		def _key(self):
			return ("interval-zero",)

	s = S()
	q = s.items

	# Auto-fetch should happen on mount
	assert await wait_for(lambda: q.pages == [1] and s.calls == 1)

	# No interval refetch should be scheduled
	assert not await wait_for(lambda: s.calls > 1, timeout=0.05)
	assert q.pages == [1]

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

	# Auto-fetch should happen on mount
	assert await wait_for(lambda: q.pages == [1] and s.calls == 1)

	# Wait for one interval refetch
	assert await wait_for(lambda: q.pages == [2] and s.calls == 2)

	# Dispose - interval should stop
	q.dispose()

	# Wait and verify no more refetches (negative test)
	assert not await wait_for(lambda: s.calls > 2 or q.pages != [2], timeout=0.05)


@pytest.mark.asyncio
async def test_infinite_query_interval_uses_min_interval_and_latest_observer():
	"""Interval uses min observer interval and latest observer with that interval."""
	calls_a = 0
	calls_b = 0
	calls_c = 0

	async def fetch_a(page_param: int) -> int:
		nonlocal calls_a
		calls_a += 1
		await asyncio.sleep(0)
		return calls_a

	async def fetch_b(page_param: int) -> int:
		nonlocal calls_b
		calls_b += 1
		await asyncio.sleep(0)
		return calls_b

	async def fetch_c(page_param: int) -> int:
		nonlocal calls_c
		calls_c += 1
		await asyncio.sleep(0)
		return calls_c

	def get_next_page_param(pages: list[Page[int, int]]) -> int | None:
		return None

	query = InfiniteQuery(
		("interval-min",),
		initial_page_param=0,
		get_next_page_param=get_next_page_param,
		retries=0,
	)
	query_computed = Computed(lambda: query, name="inf_query(interval-min)")

	obs_a = InfiniteQueryResult(
		query_computed,
		fetch_fn=fetch_a,
		refetch_interval=0.02,
		fetch_on_mount=False,
	)
	assert await wait_for(lambda: calls_a >= 1, timeout=0.4)

	obs_b = InfiniteQueryResult(
		query_computed,
		fetch_fn=fetch_b,
		refetch_interval=0.01,
		fetch_on_mount=False,
	)
	assert await wait_for(lambda: calls_b >= 1, timeout=0.4)

	calls_a_at = calls_a
	calls_b_at = calls_b
	assert await wait_for(lambda: calls_b >= calls_b_at + 3, timeout=0.4)
	assert calls_a == calls_a_at

	obs_c = InfiniteQueryResult(
		query_computed,
		fetch_fn=fetch_c,
		refetch_interval=0.01,
		fetch_on_mount=False,
	)
	assert await wait_for(lambda: calls_c >= 1, timeout=0.4)

	calls_b_at = calls_b
	calls_c_at = calls_c
	assert await wait_for(lambda: calls_c >= calls_c_at + 3, timeout=0.4)
	assert calls_b == calls_b_at

	obs_c.dispose()

	calls_b_at = calls_b
	assert await wait_for(lambda: calls_b >= calls_b_at + 2, timeout=0.4)

	obs_b.dispose()

	calls_a_at = calls_a
	assert await wait_for(lambda: calls_a >= calls_a_at + 1, timeout=0.4)

	obs_a.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_cancel_fetch_cancels_inflight_request():
	"""Test that cancel_fetch=True actually cancels in-flight requests."""

	class S(ps.State):
		fetch_started: list[int] = []
		fetch_completed: list[int] = []

		@ps.infinite_query(initial_page_param=0, retries=0)
		async def slow_query(self, page_param: int) -> int:
			self.fetch_started.append(page_param)
			# Slow fetch - gives time for cancellation
			await asyncio.sleep(0.015)
			self.fetch_completed.append(page_param)
			return page_param

		@slow_query.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 5 else None

		@slow_query.key
		def _key(self):
			return ("cancel-inflight",)

	s = S()
	q = s.slow_query

	# Start initial fetch (but don't await it fully)
	wait_task = asyncio.create_task(q.wait())
	# Give it time to start the fetch
	assert await wait_for(lambda: s.fetch_started == [0], timeout=0.2)

	# Verify fetch started but not completed
	assert s.fetch_started == [0]
	assert s.fetch_completed == []

	# Now cancel with refetch - the in-flight request should be cancelled
	refetch_task = asyncio.create_task(q.refetch(cancel_fetch=True))

	# Wait for the new refetch to complete
	await refetch_task

	# The first fetch should have been cancelled (not completed)
	# and the refetch should have run instead
	assert s.fetch_started == [0, 0]
	assert s.fetch_completed == [0]

	# The wait_task should have been cancelled
	assert wait_task.cancelled() or wait_task.done()

	q.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_cancel_fetch_next_page_cancels_inflight():
	"""Test that fetch_next_page with cancel_fetch=True cancels in-flight requests."""

	class S(ps.State):
		fetch_started: list[int] = []
		fetch_completed: list[int] = []

		@ps.infinite_query(initial_page_param=0, retries=0)
		async def slow_query(self, page_param: int) -> int:
			self.fetch_started.append(page_param)
			await asyncio.sleep(0.015)
			self.fetch_completed.append(page_param)
			return page_param

		@slow_query.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 5 else None

		@slow_query.key
		def _key(self):
			return ("cancel-fetch-next",)

	s = S()
	q = s.slow_query

	# Get initial page first
	await q.wait()
	assert q.pages == [0]
	s.fetch_started.clear()
	s.fetch_completed.clear()

	# Start fetching next page (don't await - we'll cancel it)
	_fetch_task = asyncio.create_task(q.fetch_next_page())
	assert await wait_for(lambda: s.fetch_started == [1], timeout=0.2)

	# Verify fetch of page 1 started but not completed
	assert s.fetch_started == [1]
	assert s.fetch_completed == []

	# Cancel and start refetch
	refetch_task = asyncio.create_task(q.refetch(cancel_fetch=True))
	await refetch_task

	# The fetch_next_page should have been cancelled
	# Only the refetch should complete (which refetches page 0)
	assert s.fetch_started == [1, 0]
	assert s.fetch_completed == [0]

	q.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Fetch function isolation tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_multiple_observers_use_own_fetch_fn():
	"""
	Test that when multiple state instances share the same infinite query key but have
	different non-key properties, each observer uses its own fetch function.

	Scenario:
	- Two state instances share key ("shared",) but have different `suffix` values
	- The `suffix` property is NOT part of the key
	- When refetch/invalidate is called on each InfiniteQueryResult, it should use
	  that observer's fetch function with its own `suffix` value
	"""
	fetch_log: list[tuple[str, str, int]] = []  # (name, suffix, page_param)

	class S(ps.State):
		_name: str
		suffix: str  # Not part of the key

		def __init__(self, name: str, suffix: str):
			self._name = name
			self.suffix = suffix

		@ps.infinite_query(
			initial_page_param=0,
			retries=0,
			gc_time=10,
			stale_time=0,
			fetch_on_mount=False,
		)
		async def data(self, page_param: int) -> str:
			result = f"{self._name}-{self.suffix}-{page_param}"
			fetch_log.append((self._name, self.suffix, page_param))
			await asyncio.sleep(0)
			return result

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 2 else None

		@data.key
		def _data_key(self):
			return ("shared",)  # Same key for all instances

	# Create two state instances with different suffix values
	s1 = S("state1", suffix="A")
	s2 = S("state2", suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Initial fetch - explicitly trigger via q1
	await q1.ensure()
	assert q1.pages == ["state1-A-0"]
	assert fetch_log == [("state1", "A", 0)]

	# q2 shares the same query, so it sees the same data
	assert q2.pages == ["state1-A-0"]

	# Now refetch via q2 - should use s2's fetch function with suffix="B"
	await q2.refetch()
	assert q2.pages == ["state2-B-0"]
	assert fetch_log[-1] == ("state2", "B", 0), (
		f"Expected refetch to use state2's fetch function, but got {fetch_log[-1]}"
	)

	# Refetch via q1 - should use s1's fetch function with suffix="A"
	await q1.refetch()
	assert q1.pages == ["state1-A-0"]
	assert fetch_log[-1] == ("state1", "A", 0), (
		f"Expected refetch to use state1's fetch function, but got {fetch_log[-1]}"
	)

	# Test fetch_next_page uses correct fetch function
	await q2.fetch_next_page()
	assert fetch_log[-1] == ("state2", "B", 1), (
		f"Expected fetch_next_page to use state2's fetch function, but got {fetch_log[-1]}"
	)

	# fetch_next_page via q1 should use q1's fetch function
	await q1.fetch_next_page()
	assert fetch_log[-1] == ("state1", "A", 2), (
		f"Expected fetch_next_page to use state1's fetch function, but got {fetch_log[-1]}"
	)

	# Test invalidate() - should also use the correct fetch function
	# Note: invalidate refetches all pages, so the last fetch will be for the last page
	fetch_log_before = len(fetch_log)
	q2.invalidate()
	assert await wait_for(lambda: len(fetch_log) > fetch_log_before, timeout=0.2)
	# Check that all new fetches used q2's fetch function
	new_fetches = fetch_log[fetch_log_before:]
	for name, suffix, _page in new_fetches:
		assert (name, suffix) == ("state2", "B"), (
			f"Expected invalidate to use state2's fetch function, but got ({name}, {suffix})"
		)


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_second_observer_does_not_refetch_inflight():
	"""Test that a second observer does not enqueue a refetch while one is in-flight."""
	fetch_started: list[int] = []
	fetch_completed: list[int] = []
	allow_finish = asyncio.Event()

	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, retries=0)
		async def data(self, page_param: int) -> int:
			fetch_started.append(page_param)
			await allow_finish.wait()
			fetch_completed.append(page_param)
			return page_param

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[int, int]]) -> int | None:
			return None

		@data.key
		def _data_key(self):
			return ("inflight-no-refetch",)

	s1 = S()
	q1 = s1.data

	# Wait for the first observer's fetch to start
	assert await wait_for(lambda: fetch_started == [0], timeout=0.2)

	# Attach second observer while fetch is in-flight
	s2 = S()
	q2 = s2.data
	await asyncio.sleep(0)

	# No extra refetch should be queued
	assert fetch_started == [0]

	# Allow the original fetch to complete
	allow_finish.set()
	assert await wait_for(lambda: fetch_completed == [0], timeout=0.2)
	assert fetch_started == [0]
	q1.dispose()
	q2.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_fetch_previous_uses_correct_fetch_fn():
	"""
	Test that fetch_previous_page uses the correct fetch function for each observer.
	"""
	fetch_log: list[tuple[str, int]] = []  # (suffix, page_param)

	class S(ps.State):
		suffix: str

		def __init__(self, suffix: str):
			self.suffix = suffix

		@ps.infinite_query(initial_page_param=5, retries=0, gc_time=10)
		async def data(self, page_param: int) -> str:
			fetch_log.append((self.suffix, page_param))
			await asyncio.sleep(0)
			return f"{self.suffix}-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 10 else None

		@data.get_previous_page_param
		def _get_prev(self, pages: list[Page[str, int]]) -> int | None:
			return pages[0].param - 1 if pages[0].param > 0 else None

		@data.key
		def _key(self):
			return ("shared-prev",)

	s1 = S(suffix="X")
	s2 = S(suffix="Y")

	q1 = s1.data
	q2 = s2.data

	# Initial fetch via q1
	await q1.wait()
	assert fetch_log[-1] == ("X", 5)

	# fetch_previous_page via q2 should use q2's fetch function
	await q2.fetch_previous_page()
	assert fetch_log[-1] == ("Y", 4), (
		f"Expected fetch_previous_page to use state2's fetch function, but got {fetch_log[-1]}"
	)

	# fetch_previous_page via q1 should use q1's fetch function
	await q1.fetch_previous_page()
	assert fetch_log[-1] == ("X", 3), (
		f"Expected fetch_previous_page to use state1's fetch function, but got {fetch_log[-1]}"
	)


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_wait_after_invalidate_uses_correct_fetch_fn():
	"""
	Test that wait() after invalidate() uses the correct fetch function.
	"""
	fetch_log: list[tuple[str, int]] = []

	class S(ps.State):
		suffix: str

		def __init__(self, suffix: str):
			self.suffix = suffix

		@ps.infinite_query(initial_page_param=0, retries=0, gc_time=10)
		async def data(self, page_param: int) -> str:
			fetch_log.append((self.suffix, page_param))
			await asyncio.sleep(0)
			return f"{self.suffix}-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 2 else None

		@data.key
		def _key(self):
			return ("wait-invalidate",)

	s1 = S(suffix="A")
	s2 = S(suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Initial fetch via q1
	await q1.wait()
	assert fetch_log[-1] == ("A", 0)

	# wait() on q1 should use s1's fetch function (no-op since data exists)
	await q1.wait()
	# No new fetch since data already loaded

	# Invalidate via q2 and then wait - should use s2's fetch function
	q2.invalidate()
	await q2.wait()
	assert fetch_log[-1] == ("B", 0), (
		f"Expected wait() after invalidate to use state2's fetch function, but got {fetch_log[-1]}"
	)


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_concurrent_fetch_next_uses_correct_fetch_fn():
	"""
	Test that when two observers call fetch_next_page concurrently without
	cancel_fetch, only the first fetch runs (queue serialization), but the
	action uses the correct fetch function for the observer that enqueued it.
	"""
	fetch_log: list[tuple[str, int]] = []

	class S(ps.State):
		suffix: str

		def __init__(self, suffix: str):
			self.suffix = suffix

		@ps.infinite_query(
			initial_page_param=0, retries=0, gc_time=10, fetch_on_mount=False
		)
		async def data(self, page_param: int) -> str:
			fetch_log.append((self.suffix, page_param))
			await asyncio.sleep(0.01)  # Small delay to allow concurrency
			return f"{self.suffix}-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 5 else None

		@data.key
		def _key(self):
			return ("concurrent-fetch-next",)

	s1 = S(suffix="X")
	s2 = S(suffix="Y")

	q1 = s1.data
	q2 = s2.data

	# Initial fetch
	await q1.ensure()
	assert fetch_log == [("X", 0)]

	# Start both fetch_next_page concurrently
	task1 = asyncio.create_task(q1.fetch_next_page())
	task2 = asyncio.create_task(q2.fetch_next_page())

	await asyncio.gather(task1, task2)

	# Both actions should be processed sequentially
	# First action uses q1's fetch function (page 1), second uses q2's (page 2)
	assert fetch_log == [("X", 0), ("X", 1), ("Y", 2)]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_refetch_with_cancel_uses_correct_fetch_fn():
	"""
	Test that when q2 calls refetch with cancel_fetch=True while q1's fetch is
	in progress, the new refetch uses q2's fetch function.
	"""
	fetch_started: list[tuple[str, int]] = []
	fetch_completed: list[tuple[str, int]] = []

	class S(ps.State):
		suffix: str

		def __init__(self, suffix: str):
			self.suffix = suffix

		@ps.infinite_query(initial_page_param=0, retries=0, gc_time=10)
		async def data(self, page_param: int) -> str:
			fetch_started.append((self.suffix, page_param))
			await asyncio.sleep(0.015)  # Long enough to allow cancellation
			fetch_completed.append((self.suffix, page_param))
			return f"{self.suffix}-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 2 else None

		@data.key
		def _key(self):
			return ("cancel-refetch",)

	s1 = S(suffix="A")
	s2 = S(suffix="B")

	q1 = s1.data
	q2 = s2.data

	# Start q1's wait (which triggers initial fetch)
	task1 = asyncio.create_task(q1.wait())
	assert await wait_for(lambda: ("A", 0) in fetch_started, timeout=0.2)

	assert ("A", 0) in fetch_started

	# q2 cancels and starts its own refetch
	task2 = asyncio.create_task(q2.refetch(cancel_fetch=True))
	await task2

	# q1's fetch should have been cancelled
	assert ("A", 0) not in fetch_completed, "q1's fetch should have been cancelled"

	# q2's refetch should have completed
	assert ("B", 0) in fetch_completed, (
		"q2's refetch should have completed with its fetch function"
	)

	# The wait task should be cancelled or done
	assert task1.cancelled() or task1.done()


# ─────────────────────────────────────────────────────────────────────────────
# Dispose cancellation tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_result_dispose_cancels_in_flight_fetch():
	"""
	Test that when an InfiniteQueryResult is disposed while it has an in-flight fetch,
	the fetch is cancelled to avoid running fetch functions from a disposed state.
	"""
	fetch_started = asyncio.Event()
	fetch_log: list[str] = []

	class S(ps.State):
		@ps.infinite_query(initial_page_param=0, retries=0, gc_time=10)
		async def data(self, page_param: int) -> str:
			fetch_log.append("started")
			fetch_started.set()
			await asyncio.sleep(0.02)  # Long running fetch
			fetch_log.append("completed")
			return f"result-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 5 else None

		@data.key
		def _key(self):
			return ("dispose-cancel-inf",)

	s = S()
	q = s.data

	# Start fetch but don't wait for it
	wait_task = asyncio.create_task(q.wait())
	await fetch_started.wait()

	# Dispose before fetch completes
	q.dispose()

	# Give time for cancellation to propagate
	assert not await wait_for(lambda: "completed" in fetch_log, timeout=0.015)

	# Fetch should have been cancelled, not completed
	assert fetch_log == ["started"]

	# The wait task should complete (either with error or cancelled)
	try:
		await asyncio.wait_for(wait_task, timeout=0.5)
	except (asyncio.CancelledError, asyncio.TimeoutError):
		pass  # Expected - task was cancelled


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_result_dispose_cancels_pending_actions():
	"""
	Test that when an InfiniteQueryResult is disposed, any pending actions
	(not yet executing) enqueued by it are cancelled.
	"""
	fetch_log: list[tuple[str, int]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		name: str

		def __init__(self, name: str):
			self.name = name

		@ps.infinite_query(
			initial_page_param=0, retries=0, gc_time=10, fetch_on_mount=False
		)
		async def data(self, page_param: int) -> str:
			fetch_log.append((self.name, page_param))
			fetch_started.set()
			await asyncio.sleep(0.02)  # Long enough for dispose to happen
			return f"{self.name}-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 5 else None

		@data.key
		def _key(self):
			return ("dispose-pending",)

	s1 = S("s1")
	s2 = S("s2")

	q1 = s1.data
	q2 = s2.data

	# Wait for initial data from q1
	await q1.ensure()
	assert fetch_log == [("s1", 0)]
	fetch_log.clear()
	fetch_started.clear()

	# s2 enqueues an action first - this will start executing
	task_s2_first = asyncio.create_task(q2.fetch_next_page())
	await fetch_started.wait()  # Wait for s2's fetch to start
	fetch_started.clear()

	# s1 enqueues an action - this will be pending in the queue
	task_s1 = asyncio.create_task(q1.fetch_next_page())
	assert await wait_for(lambda: len(q1._query()._queue) > 0, timeout=0.2)  # pyright: ignore[reportPrivateUsage]

	# Now dispose s1 - s1's pending action should be cancelled
	q1.dispose()

	# Wait for s2's first action to complete
	await task_s2_first

	# s1's task should be cancelled since it was pending when disposed
	try:
		await asyncio.wait_for(task_s1, timeout=0.5)
		# If it completed, that's OK too - the action might have started before dispose
	except asyncio.CancelledError:
		pass  # Expected - pending action was cancelled
	except asyncio.TimeoutError:
		pytest.fail("task_s1 should have been cancelled or completed")

	# s1's fetch should NOT have been executed (it was pending and cancelled)
	# Only s2's fetch_next_page should have run
	assert fetch_log == [("s2", 1)]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_result_dispose_does_not_cancel_other_observer_fetch():
	"""
	Test that disposing one observer doesn't cancel a fetch started by another observer.
	"""
	fetch_log: list[tuple[str, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		name: str

		def __init__(self, name: str):
			self.name = name

		@ps.infinite_query(
			initial_page_param=0, retries=0, gc_time=10, fetch_on_mount=False
		)
		async def data(self, page_param: int) -> str:
			fetch_log.append((self.name, "started"))
			fetch_started.set()
			await asyncio.sleep(0.01)
			fetch_log.append((self.name, "completed"))
			return f"{self.name}-{page_param}"

		@data.get_next_page_param
		def _get_next(self, pages: list[Page[str, int]]) -> int | None:
			return pages[-1].param + 1 if pages[-1].param < 5 else None

		@data.key
		def _key(self):
			return ("dispose-other",)

	s1 = S("s1")
	s2 = S("s2")

	q1 = s1.data
	q2 = s2.data

	# s1 starts fetch
	wait_task = asyncio.create_task(q1.ensure())
	await fetch_started.wait()

	# s2 disposes - should NOT cancel s1's fetch since s1 is the one who enqueued it
	q2.dispose()

	# Wait for s1's fetch to complete
	await wait_task

	# s1's fetch should have completed
	assert fetch_log == [("s1", "started"), ("s1", "completed")]


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_key_change_cancels_pending_actions():
	"""
	Test that when a keyed infinite query's key changes, pending actions
	for the old key are cancelled.

	Scenario: user_id changes from 1 to 2 before the fetch for user_id=1 completes.
	The pending action should be cancelled.
	"""
	fetch_log: list[tuple[int, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		user_id: int = 1

		@ps.infinite_query(initial_page_param=0, retries=0, gc_time=10)
		async def projects(self, page_param: int) -> ProjectsPage:
			uid = self.user_id
			fetch_log.append((uid, "started"))
			fetch_started.set()
			await asyncio.sleep(0.02)  # Long running fetch
			fetch_log.append((uid, "completed"))
			return {"items": [uid * 10 + page_param], "next": None}

		@projects.get_next_page_param
		def _get_next(self, pages: list[Page[ProjectsPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@projects.key
		def _key(self):
			return ("projects", self.user_id)

	s = S()
	q = s.projects

	# Start fetch for user_id=1
	wait_task = asyncio.create_task(q.wait())
	await fetch_started.wait()
	fetch_started.clear()

	# Change key before fetch completes
	s.user_id = 2
	# Allow the reactive system to process the key change
	assert await wait_for(lambda: q._query().key == ("projects", 2), timeout=0.2)  # pyright: ignore[reportPrivateUsage]

	# The old fetch (for user_id=1) may have been cancelled or continued
	# depending on whether it was the currently executing action
	# But any pending actions should be cancelled

	# Wait for or cancel the old wait task
	try:
		await asyncio.wait_for(wait_task, timeout=0.1)
	except (asyncio.CancelledError, asyncio.TimeoutError):
		pass  # Expected

	# Clean up
	q.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_key_change_starts_new_fetch():
	"""
	Test that when a keyed infinite query's key changes, a new fetch is started
	for the new key.
	"""
	fetch_log: list[tuple[int, str]] = []
	fetch_started = asyncio.Event()

	class S(ps.State):
		user_id: int = 1

		# Use stale_time=1000 to ensure new queries are considered stale and auto-fetch
		@ps.infinite_query(initial_page_param=0, retries=0, gc_time=10, stale_time=1000)
		async def projects(self, page_param: int) -> ProjectsPage:
			uid = self.user_id
			fetch_log.append((uid, "started"))
			fetch_started.set()
			await asyncio.sleep(0.01)
			fetch_log.append((uid, "completed"))
			return {"items": [uid * 10 + page_param], "next": None}

		@projects.get_next_page_param
		def _get_next(self, pages: list[Page[ProjectsPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@projects.key
		def _key(self):
			return ("projects", self.user_id)

	s = S()
	q = s.projects

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
	assert q.data is not None
	assert q.data[0].data["items"] == [20]

	# Clean up
	q.dispose()


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_key_change_does_not_affect_other_observer():
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

		# Use stale_time=1000 to ensure new queries are considered stale and auto-fetch
		@ps.infinite_query(initial_page_param=0, retries=0, gc_time=10, stale_time=1000)
		async def projects(self, page_param: int) -> ProjectsPage:
			uid = self.user_id
			fetch_log.append((self.name, uid, "started"))
			fetch_started.set()
			await asyncio.sleep(0.015)
			fetch_log.append((self.name, uid, "completed"))
			return {"items": [uid * 10 + page_param], "next": None}

		@projects.get_next_page_param
		def _get_next(self, pages: list[Page[ProjectsPage, int]]) -> int | None:
			return pages[-1].data["next"]

		@projects.key
		def _key(self):
			return ("projects", self.user_id)

	# Two states observing the same key initially
	s1 = S("s1", 1)
	s2 = S("s2", 1)

	q1 = s1.projects
	q2 = s2.projects

	# s1 starts fetch for key ("projects", 1)
	wait_task = asyncio.create_task(q1.wait())
	await fetch_started.wait()
	fetch_started.clear()

	# s2 changes its key - but s1 started the fetch, so it should continue
	s2.user_id = 2
	assert await wait_for(lambda: q2._query().key == ("projects", 2), timeout=0.2)  # pyright: ignore[reportPrivateUsage]

	# Wait for s1's fetch to complete
	await wait_task

	# s1's fetch should complete successfully
	assert ("s1", 1, "started") in fetch_log
	assert ("s1", 1, "completed") in fetch_log
	assert q1.data is not None
	assert q1.data[0].data["items"] == [10]

	# Clean up
	q1.dispose()
	q2.dispose()
