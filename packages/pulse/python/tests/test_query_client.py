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
	# Use the @ps.query decorator to create a query with proper fetch function
	class S(ps.State):
		@ps.query(retries=0)
		async def user(self) -> str:
			return "initial"

		@user.key
		def _user_key(self):
			return ("user", 1)

	s = S()
	q = s.user

	# Wait for the fetch to complete
	await q.wait()

	# Get via client
	assert ps.queries.get(("user", 1)) is not None
	assert ps.queries.get_data(("user", 1)) == "initial"

	# Set via client
	assert ps.queries.set_data(("user", 1), "updated") is True
	assert ps.queries.get_data(("user", 1)) == "updated"
	assert ps.queries.set_data(["user", 1], "list-updated") is True
	assert ps.queries.get_data(("user", 1)) == "list-updated"

	# Non-existent key returns False
	assert ps.queries.set_data(("missing",), "x") is False
	assert ps.queries.set_data(["missing"], "x") is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_get_all_with_filters():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	# Create several queries (fetcher is now provided by QueryResult, not store.ensure)
	store.ensure(("users", 1))
	store.ensure(("users", 2))
	store.ensure(("posts", 1))

	# Get all
	all_queries = ps.queries.get_all()
	assert len(all_queries) == 3

	# Filter by exact key
	exact = ps.queries.get_all(("users", 1))
	assert len(exact) == 1
	assert exact[0].key == ("users", 1)

	# Filter by multiple keys
	by_keys = ps.queries.get_all(ps.keys(("users", 1), ("posts", 1)))
	assert len(by_keys) == 2

	# Filter by predicate
	users = ps.queries.get_all(lambda k: k[0] == "users")
	assert len(users) == 2


@pytest.mark.asyncio
@with_render_session
async def test_query_client_filter_with_query_keys_wrapper():
	"""Test that QueryFilter works with QueryKeys and list keys."""
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	# Create queries with list keys
	store.ensure(["users", 1])
	store.ensure(["users", 2])
	store.ensure(["posts", 1])

	# Filter by exact list key
	exact = ps.queries.get_all(["users", 1])
	assert len(exact) == 1
	assert exact[0].key == ("users", 1)  # Stored as tuple

	# Filter by QueryKeys with list keys
	by_keys = ps.queries.get_all(ps.keys(["users", 1], ["posts", 1]))
	assert len(by_keys) == 2

	# Mix list and tuple keys in QueryKeys
	by_mixed = ps.queries.get_all(ps.keys(["users", 1], ("users", 2)))
	assert len(by_mixed) == 2


@pytest.mark.asyncio
@with_render_session
async def test_query_client_prefix_operations():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	# Create queries with nested keys (fetcher is now provided by QueryResult, not store.ensure)
	store.ensure(("api", "users", 1))
	store.ensure(("api", "users", 2))
	store.ensure(("api", "posts", 1))
	store.ensure(("cache", "items"))

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

	# Create query (fetcher is now provided by QueryResult, not store.ensure)
	store.ensure(("test",))

	# Invalidate returns True if query exists
	assert ps.queries.invalidate(("test",)) is True
	assert ps.queries.invalidate(["test"]) is True
	assert ps.queries.invalidate(("missing",)) is False
	assert ps.queries.invalidate(["missing"]) is False


@pytest.mark.asyncio
@with_render_session
async def test_query_client_invalidate_all():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	# Create queries (fetcher is now provided by QueryResult, not store.ensure)
	store.ensure(("a",))
	store.ensure(("b",))

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

	def get_next(pages: list[Page[list[str], int]]):
		return pages[-1].param + 1 if pages else 0

	# Create infinite query (without fetcher - fetcher is now provided by InfiniteQueryResult)
	inf_query = store.ensure_infinite(
		("items",),
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

	# Query without initial_data starts as loading
	query = store.ensure(("test",))
	# Note: Without initial_data, query starts in loading state
	assert ps.queries.is_loading() is True

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
	# Use the @ps.query decorator to create a query with proper fetch function
	class S(ps.State):
		@ps.query(retries=0)
		async def data(self) -> str:
			return "data"

		@data.key
		def _data_key(self):
			return ("test",)

	s = S()
	query = s.data
	await query.wait()

	# Set error via client
	error = ValueError("test error")
	assert ps.queries.set_error(("test",), error) is True
	assert query.status == "error"
	assert query.error is error

	# Non-existent key
	assert ps.queries.set_error(("missing",), error) is False


# ─────────────────────────────────────────────────────────────────────────────
# Remove tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@with_render_session
async def test_query_client_remove():
	store = ps.PulseContext.get().render.query_store  # pyright: ignore[reportOptionalMemberAccess]

	# Create queries (fetcher is now provided by QueryResult, not store.ensure)
	store.ensure(("a",))
	store.ensure(("b",))

	assert len(ps.queries.get_all()) == 2

	# Remove single
	assert ps.queries.remove(("a",)) is True
	assert ps.queries.remove(("a",)) is False  # Already removed
	assert len(ps.queries.get_all()) == 1

	# Remove all
	store.ensure(("c",))
	count = ps.queries.remove_all()
	assert count == 2
	assert len(ps.queries.get_all()) == 0
