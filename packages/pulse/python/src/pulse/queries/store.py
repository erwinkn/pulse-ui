from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from pulse.queries.infinite_query import InfiniteQuery
from pulse.queries.query import RETRY_DELAY_DEFAULT, Query, QueryKey

T = TypeVar("T")


class QueryStore:
	"""
	Store for query entries. Manages creation, retrieval, and disposal of queries.
	"""

	def __init__(self):
		self._entries: dict[QueryKey, Query[Any]] = {}

	def get(self, key: QueryKey) -> Query[Any] | None:
		return self._entries.get(key)

	def ensure(
		self,
		key: QueryKey,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None = None,
		gc_time: float = 300.0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
	) -> Query[T]:
		# Return existing entry if present
		existing = self._entries.get(key)
		if existing:
			if isinstance(existing, InfiniteQuery):
				raise TypeError(
					"Query key is already used for an infinite query; cannot reuse for regular query"
				)
			return cast(Query[T], existing)

		def _on_dispose(e: Query[Any]) -> None:
			if e.key in self._entries and self._entries[e.key] is e:
				del self._entries[e.key]

		entry = Query(
			key,
			fetch_fn,
			initial_data=initial_data,
			gc_time=gc_time,
			retries=retries,
			retry_delay=retry_delay,
			on_dispose=_on_dispose,
		)
		self._entries[key] = entry
		return entry

	def ensure_infinite(
		self,
		key: QueryKey,
		query_fn: Callable[[Any], Awaitable[Any]],
		*,
		initial_page_param: Any,
		get_next_page_param: Callable[[Any, list[Any], Any, list[Any]], Any | None],
		get_previous_page_param: Callable[[Any, list[Any], Any, list[Any]], Any | None]
		| None = None,
		max_pages: int = 0,
		gc_time: float = 300.0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
	) -> InfiniteQuery[Any, Any]:
		existing = self._entries.get(key)
		if existing:
			if not isinstance(existing, InfiniteQuery):
				raise TypeError(
					"Query key is already used for a regular query; cannot reuse for infinite query"
				)
			return existing

		def _on_dispose(e: InfiniteQuery[Any, Any]) -> None:
			if e.key in self._entries and self._entries[e.key] is e:
				del self._entries[e.key]

		entry = InfiniteQuery(
			key,
			query_fn,
			initial_page_param=initial_page_param,
			get_next_page_param=get_next_page_param,
			get_previous_page_param=get_previous_page_param,
			max_pages=max_pages,
			gc_time=gc_time,
			retries=retries,
			retry_delay=retry_delay,
			on_dispose=_on_dispose,
		)
		self._entries[key] = entry
		return entry

	def remove(self, key: QueryKey):
		entry = self._entries.get(key)
		if entry:
			entry.dispose()

	def get_queries(
		self, predicate: Callable[[Query[Any]], bool] | None = None
	) -> list[Query[Any]]:
		"""Get all queries matching the predicate."""
		if predicate is None:
			return list(self._entries.values())
		return [e for e in self._entries.values() if predicate(e)]
