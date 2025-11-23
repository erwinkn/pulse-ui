import asyncio
from collections.abc import Awaitable, Callable

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import RouteTree


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	"""Set up a PulseContext with an App for all tests."""
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def with_render_session(fn: Callable[..., Awaitable[object]]):
	"""Decorator to wrap test functions with a RenderSession context."""

	async def wrapper(*args, **kwargs):
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

		@ps.infinite_query(
			initial_page_param=0,
			get_next_page_param=lambda last, pages, last_param, params: last["next"],
			retries=0,
		)
		async def projects(self, ctx):
			self.calls += 1
			await asyncio.sleep(0)
			next_val = ctx.page_param + 1 if ctx.page_param < 2 else None
			return {"items": [ctx.page_param], "next": next_val}

		@projects.key
		def _key(self):
			return ("projects",)

	s = S()
	q = s.projects

	await q.wait()
	assert q.pages == [{"items": [0], "next": 1}]
	assert q.has_next_page is True

	await q.fetch_next_page()
	assert [p["items"][0] for p in q.pages] == [0, 1]
	assert q.has_next_page is True

	await q.fetch_next_page()
	assert [p["items"][0] for p in q.pages] == [0, 1, 2]
	assert q.has_next_page is False
	assert s.calls == 3


@pytest.mark.asyncio
@with_render_session
async def test_infinite_query_max_pages_trims_forward():
	class S(ps.State):
		@ps.infinite_query(
			initial_page_param=0,
			get_next_page_param=lambda last, pages, last_param, params: last_param + 1
			if last_param < 3
			else None,
			max_pages=2,
			retries=0,
		)
		async def nums(self, ctx):
			await asyncio.sleep(0)
			return ctx.page_param

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
		@ps.infinite_query(
			initial_page_param=1,
			get_next_page_param=lambda last, pages, last_param, params: last_param + 1
			if last_param < 2
			else None,
			get_previous_page_param=lambda first,
			pages,
			first_param,
			params: first_param - 1 if first_param > 0 else None,
			retries=0,
		)
		async def nums(self, ctx):
			await asyncio.sleep(0)
			return ctx.page_param

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
		@ps.infinite_query(
			initial_page_param=0,
			get_next_page_param=lambda last, pages, last_param, params: last_param + 1,
			retries=0,
		)
		async def sometimes_fail(self, ctx):
			await asyncio.sleep(0)
			if ctx.page_param == 1:
				raise RuntimeError("boom")
			return ctx.page_param

		@sometimes_fail.key
		def _key(self):
			return ("fail-page",)

	s = S()
	q = s.sometimes_fail

	await q.wait()
	assert q.pages == [0]

	with pytest.raises(RuntimeError):
		await q.fetch_next_page()

	assert q.is_error is True
	assert q.pages == [0]
	assert q.is_fetching_next_page is False
