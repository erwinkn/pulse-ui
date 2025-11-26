"""Tests for the QueryClient API (ps.queries singleton)."""

from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import pulse as ps
import pytest
from pulse.queries.infinite_query import InfiniteQuery, Page
from pulse.render_session import RenderSession
from pulse.routing import RouteTree

P = ParamSpec("P")
R = TypeVar("R")


@pytest.fixture(autouse=True)
def pulse_context():
	"""Set up a PulseContext with an App for all tests."""
	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def with_render_session(fn: Callable[P, Awaitable[R]]):
	"""Decorator to wrap test functions with a RenderSession context."""

	async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
		routes = RouteTree([])
		session = RenderSession("test-session", routes)
		with ps.PulseContext.update(render=session):
			return await fn(*args, **kwargs)

	return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Basic get/set tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_get_returns_none_for_missing():
	assert ps.queries.get(("missing",)) is None
	assert ps.queries.get_infinite(("missing",)) is None


@pytest.mark.asyncio
@with_render_session
async def test_query_client_get_and_set_data():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	# Create a query in the store
	async def fetcher():
		return "initial"

	query = store.ensure(("user", 1), fetcher)
	await query.refetch()

	# Get via client
	assert ps.queries.get(("user", 1)) is query
	assert ps.queries.get_data(("user", 1)) == "initial"

	# Set via client
	assert ps.queries.set_data(("user", 1), "updated") is True
	assert ps.queries.get_data(("user", 1)) == "updated"

	# Non-existent key returns False
	assert ps.queries.set_data(("missing",), "x") is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_get_all_with_filters():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	# Create several queries
	store.ensure(("users", 1), fetcher)
	store.ensure(("users", 2), fetcher)
	store.ensure(("posts", 1), fetcher)

	# Get all
	all_queries = ps.queries.get_all()
	assert len(all_queries) == 3

	# Filter by exact key
	exact = ps.queries.get_all(("users", 1))
	assert len(exact) == 1
	assert exact[0].key == ("users", 1)

	# Filter by list of keys
	by_list = ps.queries.get_all([("users", 1), ("posts", 1)])
	assert len(by_list) == 2

	# Filter by predicate
	users = ps.queries.get_all(lambda k: k[0] == "users")
	assert len(users) == 2


@pytest.mark.asyncio
@with_render_session
async def test_query_client_prefix_operations():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	# Create queries with nested keys
	store.ensure(("api", "users", 1), fetcher)
	store.ensure(("api", "users", 2), fetcher)
	store.ensure(("api", "posts", 1), fetcher)
	store.ensure(("cache", "items"), fetcher)

	# Invalidate by prefix returns count
	count = ps.queries.invalidate_prefix(("api", "users"))
	assert count == 2

	# Remove by prefix
	count = ps.queries.remove_prefix(("api",))
	assert count == 3
	assert ps.queries.get(("cache", "items")) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Invalidation tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_invalidate_single_key():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	store.ensure(("test",), fetcher)

	# Invalidate returns True if query exists
	assert ps.queries.invalidate(("test",)) is True
	assert ps.queries.invalidate(("missing",)) is False


@pytest.mark.asyncio
@with_render_session
async def test_query_client_invalidate_all():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	store.ensure(("a",), fetcher)
	store.ensure(("b",), fetcher)

	# Invalidate all (None filter) returns count
	count = ps.queries.invalidate()
	assert count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Infinite query tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_infinite_queries():
	render = ps.PulseContext.get().render
	assert render is not None
	store = render.query_store

	async def fetcher(page: int):
		return [f"item-{page}"]

	def get_next(pages: list[Page[list[str], int]]):
		return pages[-1].param + 1 if pages else 0

	# Create infinite query
	inf_query = store.ensure_infinite(
		("items",),
		fetcher,
		initial_page_param=0,
		get_next_page_param=get_next,
	)

	# Should find it via get_infinite
	assert ps.queries.get_infinite(("items",)) is inf_query
	assert ps.queries.get(("items",)) is None  # Regular get returns None

	# get_all includes infinite by default
	all_q = ps.queries.get_all()
	assert len(all_q) == 1
	assert isinstance(all_q[0], InfiniteQuery)

	# Can exclude infinite
	regular_only = ps.queries.get_all(include_infinite=False)
	assert len(regular_only) == 0

	# get_infinite_queries
	inf_only = ps.queries.get_infinite_queries()
	assert len(inf_only) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Status checks
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_status_checks():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	# Query with initial_data=None starts as success (not loading)
	query = store.ensure(("test",), fetcher)
	assert ps.queries.is_loading() is False

	# Manually set to loading state for testing
	query.status.write("loading")
	assert ps.queries.is_loading() is True

	# Filter works
	assert ps.queries.is_loading(("test",)) is True
	assert ps.queries.is_loading(("other",)) is False


# ─────────────────────────────────────────────────────────────────────────────
# Error handling
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_set_error():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	query = store.ensure(("test",), fetcher)
	await query.refetch()

	# Set error via client
	error = ValueError("test error")
	assert ps.queries.set_error(("test",), error) is True
	assert query.status() == "error"
	assert query.error() is error

	# Non-existent key
	assert ps.queries.set_error(("missing",), error) is False


# ─────────────────────────────────────────────────────────────────────────────
# Remove tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_remove():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	async def fetcher():
		return "data"

	store.ensure(("a",), fetcher)
	store.ensure(("b",), fetcher)

	assert len(ps.queries.get_all()) == 2

	# Remove single
	assert ps.queries.remove(("a",)) is True
	assert ps.queries.remove(("a",)) is False  # Already removed
	assert len(ps.queries.get_all()) == 1

	# Remove all
	store.ensure(("c",), fetcher)
	count = ps.queries.remove_all()
	assert count == 2
	assert len(ps.queries.get_all()) == 0
