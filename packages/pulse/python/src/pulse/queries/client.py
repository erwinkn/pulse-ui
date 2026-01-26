import datetime as dt
from collections.abc import Callable, Hashable
from typing import Any, TypeVar, overload

from pulse.context import PulseContext
from pulse.helpers import MISSING
from pulse.queries.common import ActionResult, QueryKey, QueryKeys, normalize_key
from pulse.queries.infinite_query import InfiniteQuery, Page
from pulse.queries.query import KeyedQuery
from pulse.queries.store import QueryStore

T = TypeVar("T")

# Query filter types
QueryFilter = (
	QueryKey  # exact key match (tuple or list)
	| QueryKeys  # explicit set of keys
	| Callable[[tuple[Hashable, ...]], bool]  # predicate function
)


def _normalize_filter(
	filter: QueryFilter | None,
) -> tuple[tuple[Hashable, ...] | None, Callable[[tuple[Hashable, ...]], bool] | None]:
	"""Return normalized exact key (if any) and a predicate for filtering."""
	if filter is None:
		return None, None
	if callable(filter):
		return None, filter
	if isinstance(filter, QueryKeys):
		key_set = set(filter.keys)
		return None, lambda k: k in key_set
	exact_key = normalize_key(filter)
	return exact_key, lambda k: k == exact_key


def _prefix_filter(prefix: QueryKey) -> Callable[[tuple[Hashable, ...]], bool]:
	"""Create a predicate that matches keys starting with the given prefix."""
	normalized = normalize_key(prefix)
	prefix_len = len(normalized)
	return lambda k: len(k) >= prefix_len and k[:prefix_len] == normalized


class QueryClient:
	"""Client for managing queries and infinite queries in a session.

	Provides methods to get, set, invalidate, and refetch queries by key
	or using filter predicates. Automatically resolves to the current
	RenderSession's query store.

	Access via ``ps.queries`` singleton:

	Example:

	```python
	# Get query data
	user = ps.queries.get_data(("user", user_id))

	# Invalidate queries by prefix
	ps.queries.invalidate_prefix(("users",))

	# Set data optimistically
	ps.queries.set_data(("user", user_id), updated_user)

	# Check if any query is fetching
	if ps.queries.is_fetching(("user", user_id)):
	    show_loading()
	```
	"""

	def _get_store(self) -> QueryStore:
		"""Get the query store from the current PulseContext.

		Returns:
			The QueryStore from the active render session.

		Raises:
			RuntimeError: If no render session is available.
		"""
		render = PulseContext.get().render
		if render is None:
			raise RuntimeError("No render session available")
		return render.query_store

	# ─────────────────────────────────────────────────────────────────────────
	# Query accessors
	# ─────────────────────────────────────────────────────────────────────────

	def get(self, key: QueryKey) -> KeyedQuery[Any] | None:
		"""Get an existing regular query by key.

		Args:
			key: The query key tuple to look up.

		Returns:
			The KeyedQuery instance, or None if not found.
		"""
		return self._get_store().get(normalize_key(key))

	def get_infinite(self, key: QueryKey) -> InfiniteQuery[Any, Any] | None:
		"""Get an existing infinite query by key.

		Args:
			key: The query key tuple to look up.

		Returns:
			The InfiniteQuery instance, or None if not found.
		"""
		return self._get_store().get_infinite(normalize_key(key))

	def get_all(
		self,
		filter: QueryFilter | None = None,
		*,
		include_infinite: bool = True,
	) -> list[KeyedQuery[Any] | InfiniteQuery[Any, Any]]:
		"""
		Get all queries matching the filter.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, returns all queries.
			include_infinite: Whether to include infinite queries (default True).

		Returns:
			List of matching Query or InfiniteQuery instances.
		"""
		store = self._get_store()
		exact_key, predicate = _normalize_filter(filter)
		results: list[KeyedQuery[Any] | InfiniteQuery[Any, Any]] = []

		if exact_key is not None:
			if include_infinite:
				entry = store.get_any(exact_key)
			else:
				entry = store.get(exact_key)
			return [entry] if entry is not None else []

		for key, entry in store.items():
			if predicate is not None and not predicate(key):
				continue
			if not include_infinite and isinstance(entry, InfiniteQuery):
				continue
			results.append(entry)

		return results

	def get_queries(self, filter: QueryFilter | None = None) -> list[KeyedQuery[Any]]:
		"""Get all regular queries matching the filter.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, returns all regular queries.

		Returns:
			List of matching KeyedQuery instances (excludes infinite queries).
		"""
		store = self._get_store()
		exact_key, predicate = _normalize_filter(filter)
		results: list[KeyedQuery[Any]] = []

		if exact_key is not None:
			entry = store.get(exact_key)
			return [entry] if entry is not None else []

		for key, entry in store.items():
			if isinstance(entry, InfiniteQuery):
				continue
			if predicate is not None and not predicate(key):
				continue
			results.append(entry)

		return results

	def get_infinite_queries(
		self, filter: QueryFilter | None = None
	) -> list[InfiniteQuery[Any, Any]]:
		"""Get all infinite queries matching the filter.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, returns all infinite queries.

		Returns:
			List of matching InfiniteQuery instances.
		"""
		store = self._get_store()
		exact_key, predicate = _normalize_filter(filter)
		results: list[InfiniteQuery[Any, Any]] = []

		if exact_key is not None:
			entry = store.get_infinite(exact_key)
			return [entry] if entry is not None else []

		for key, entry in store.items():
			if not isinstance(entry, InfiniteQuery):
				continue
			if predicate is not None and not predicate(key):
				continue
			results.append(entry)

		return results

	# ─────────────────────────────────────────────────────────────────────────
	# Data accessors
	# ─────────────────────────────────────────────────────────────────────────

	def get_data(self, key: QueryKey) -> Any | None:
		"""Get the data for a query by key.

		Args:
			key: The query key tuple to look up.

		Returns:
			The query data, or None if query not found or has no data.
		"""
		query = self.get(key)
		if query is None:
			return None
		value = query.data.read()
		if value is MISSING:
			return None
		return value

	def get_infinite_data(self, key: QueryKey) -> list[Page[Any, Any]] | None:
		"""Get the pages for an infinite query by key.

		Args:
			key: The query key tuple to look up.

		Returns:
			List of Page objects, or None if query not found.
		"""
		query = self.get_infinite(key)
		if query is None:
			return None
		return list(query.pages)

	# ─────────────────────────────────────────────────────────────────────────
	# Data setters
	# ─────────────────────────────────────────────────────────────────────────

	@overload
	def set_data(
		self,
		key_or_filter: QueryKey,
		data: T | Callable[[T | None], T],
		*,
		updated_at: float | dt.datetime | None = None,
	) -> bool: ...

	@overload
	def set_data(
		self,
		key_or_filter: QueryKeys | Callable[[tuple[Hashable, ...]], bool],
		data: Callable[[Any], Any],
		*,
		updated_at: float | dt.datetime | None = None,
	) -> int: ...

	def set_data(
		self,
		key_or_filter: QueryKey | QueryKeys | Callable[[tuple[Hashable, ...]], bool],
		data: Any | Callable[[Any], Any],
		*,
		updated_at: float | dt.datetime | None = None,
	) -> bool | int:
		"""
		Set data for queries matching the key or filter.

		When using a single key, returns True if query exists and was updated.
		When using a filter, returns count of updated queries.

		Args:
			key_or_filter: Exact key or filter predicate.
			data: New data value or updater function.
			updated_at: Optional timestamp to set.

		Returns:
			bool if exact key, int count if filter.
		"""
		exact_key, predicate = _normalize_filter(key_or_filter)
		if exact_key is not None:
			query = self.get(exact_key)
			if query is None:
				return False
			query.set_data(data, updated_at=updated_at)
			return True

		queries = self.get_queries(predicate)
		for q in queries:
			q.set_data(data, updated_at=updated_at)
		return len(queries)

	def set_infinite_data(
		self,
		key: QueryKey,
		pages: list[Page[Any, Any]]
		| Callable[[list[Page[Any, Any]]], list[Page[Any, Any]]],
		*,
		updated_at: float | dt.datetime | None = None,
	) -> bool:
		"""Set pages for an infinite query by key.

		Args:
			key: The query key tuple.
			pages: New pages list or updater function.
			updated_at: Optional timestamp to set.

		Returns:
			True if query was found and updated, False otherwise.
		"""
		query = self.get_infinite(key)
		if query is None:
			return False
		query.set_data(pages, updated_at=updated_at)
		return True

	# ─────────────────────────────────────────────────────────────────────────
	# Invalidation
	# ─────────────────────────────────────────────────────────────────────────

	@overload
	def invalidate(
		self,
		key_or_filter: QueryKey,
		*,
		cancel_refetch: bool = False,
	) -> bool: ...

	@overload
	def invalidate(
		self,
		key_or_filter: QueryKeys | Callable[[tuple[Hashable, ...]], bool] | None = None,
		*,
		cancel_refetch: bool = False,
	) -> int: ...

	def invalidate(
		self,
		key_or_filter: QueryKey
		| QueryKeys
		| Callable[[tuple[Hashable, ...]], bool]
		| None = None,
		*,
		cancel_refetch: bool = False,
	) -> bool | int:
		"""
		Invalidate queries matching the key or filter.

		For regular queries: marks as stale and refetches if observed.
		For infinite queries: triggers refetch of all pages if observed.

		Args:
			key_or_filter: Exact key, filter predicate, or None for all.
			cancel_refetch: Cancel in-flight requests before refetch.

		Returns:
			bool if exact key, int count if filter/None.
		"""
		exact_key, predicate = _normalize_filter(key_or_filter)
		if exact_key is not None:
			query = self.get(exact_key)
			if query is not None:
				query.invalidate(cancel_refetch=cancel_refetch)
				return True
			inf_query = self.get_infinite(exact_key)
			if inf_query is not None:
				inf_query.invalidate(cancel_fetch=cancel_refetch)
				return True
			return False

		queries = self.get_all(predicate)
		for q in queries:
			if isinstance(q, InfiniteQuery):
				q.invalidate(cancel_fetch=cancel_refetch)
			else:
				q.invalidate(cancel_refetch=cancel_refetch)
		return len(queries)

	def invalidate_prefix(
		self,
		prefix: QueryKey,
		*,
		cancel_refetch: bool = False,
	) -> int:
		"""Invalidate all queries whose keys start with the given prefix.

		Args:
			prefix: Key prefix to match against query keys.
			cancel_refetch: Cancel in-flight requests before refetch.

		Returns:
			Count of invalidated queries.

		Example:

		```python
		# Invalidates ("users",), ("users", 1), ("users", 2, "posts"), etc.
		ps.queries.invalidate_prefix(("users",))
		```
		"""
		return self.invalidate(_prefix_filter(prefix), cancel_refetch=cancel_refetch)

	# ─────────────────────────────────────────────────────────────────────────
	# Refetch
	# ─────────────────────────────────────────────────────────────────────────

	async def refetch(
		self,
		key: QueryKey,
		*,
		cancel_refetch: bool = True,
	) -> ActionResult[Any] | None:
		"""Refetch a query by key and return the result.

		Args:
			key: The query key tuple to refetch.
			cancel_refetch: Cancel in-flight request before refetching (default True).

		Returns:
			ActionResult with data or error, or None if query doesn't exist.
		"""
		query = self.get(key)
		if query is not None:
			return await query.refetch(cancel_refetch=cancel_refetch)

		inf_query = self.get_infinite(key)
		if inf_query is not None:
			return await inf_query.refetch(cancel_fetch=cancel_refetch)

		return None

	async def refetch_all(
		self,
		filter: QueryFilter | None = None,
		*,
		cancel_refetch: bool = True,
	) -> list[ActionResult[Any]]:
		"""Refetch all queries matching the filter.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, refetches all queries.
			cancel_refetch: Cancel in-flight requests before refetching.

		Returns:
			List of ActionResult for each refetched query.
		"""
		queries = self.get_all(filter)
		results: list[ActionResult[Any]] = []

		for q in queries:
			if isinstance(q, InfiniteQuery):
				result = await q.refetch(cancel_fetch=cancel_refetch)
			else:
				result = await q.refetch(cancel_refetch=cancel_refetch)
			results.append(result)

		return results

	async def refetch_prefix(
		self,
		prefix: QueryKey,
		*,
		cancel_refetch: bool = True,
	) -> list[ActionResult[Any]]:
		"""Refetch all queries whose keys start with the given prefix.

		Args:
			prefix: Key prefix to match against query keys.
			cancel_refetch: Cancel in-flight requests before refetching.

		Returns:
			List of ActionResult for each refetched query.
		"""
		return await self.refetch_all(
			_prefix_filter(prefix), cancel_refetch=cancel_refetch
		)

	# ─────────────────────────────────────────────────────────────────────────
	# Error handling
	# ─────────────────────────────────────────────────────────────────────────

	def set_error(
		self,
		key: QueryKey,
		error: Exception,
		*,
		updated_at: float | dt.datetime | None = None,
	) -> bool:
		"""Set error state on a query by key.

		Args:
			key: The query key tuple.
			error: The exception to set.
			updated_at: Optional timestamp to set.

		Returns:
			True if query was found and error was set, False otherwise.
		"""
		query = self.get(key)
		if query is not None:
			query.set_error(error, updated_at=updated_at)
			return True

		inf_query = self.get_infinite(key)
		if inf_query is not None:
			inf_query.set_error(error, updated_at=updated_at)
			return True

		return False

	# ─────────────────────────────────────────────────────────────────────────
	# Reset / Remove
	# ─────────────────────────────────────────────────────────────────────────

	def remove(self, key: QueryKey) -> bool:
		"""Remove a query from the store, disposing it.

		Args:
			key: The query key tuple to remove.

		Returns:
			True if query existed and was removed, False otherwise.
		"""
		store = self._get_store()
		entry = store.get_any(normalize_key(key))
		if entry is None:
			return False
		entry.dispose()
		return True

	def remove_all(self, filter: QueryFilter | None = None) -> int:
		"""Remove all queries matching the filter.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, removes all queries.

		Returns:
			Count of removed queries.
		"""
		queries = self.get_all(filter)
		for q in queries:
			q.dispose()
		return len(queries)

	def remove_prefix(self, prefix: QueryKey) -> int:
		"""Remove all queries whose keys start with the given prefix.

		Args:
			prefix: Key prefix to match against query keys.

		Returns:
			Count of removed queries.
		"""
		return self.remove_all(_prefix_filter(prefix))

	# ─────────────────────────────────────────────────────────────────────────
	# State queries
	# ─────────────────────────────────────────────────────────────────────────

	def is_fetching(self, filter: QueryFilter | None = None) -> bool:
		"""Check if any query matching the filter is currently fetching.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, checks all queries.

		Returns:
			True if any matching query is fetching.
		"""
		queries = self.get_all(filter)
		for q in queries:
			if q.is_fetching():
				return True
		return False

	def is_loading(self, filter: QueryFilter | None = None) -> bool:
		"""Check if any query matching the filter is in loading state.

		Args:
			filter: Optional filter - exact key, QueryKeys, or predicate.
				If None, checks all queries.

		Returns:
			True if any matching query has status "loading".
		"""
		queries = self.get_all(filter)
		for q in queries:
			if isinstance(q, InfiniteQuery):
				if q.status() == "loading":
					return True
			elif q.status() == "loading":
				return True
		return False

	# ─────────────────────────────────────────────────────────────────────────
	# Wait helpers
	# ─────────────────────────────────────────────────────────────────────────

	async def wait(self, key: QueryKey) -> ActionResult[Any] | None:
		"""Wait for a query to complete and return the result.

		Args:
			key: The query key tuple to wait for.

		Returns:
			ActionResult with data or error, or None if query doesn't exist.
		"""
		query = self.get(key)
		if query is not None:
			return await query.wait()

		inf_query = self.get_infinite(key)
		if inf_query is not None:
			return await inf_query.wait()

		return None


# Singleton instance accessible via ps.queries
queries = QueryClient()
