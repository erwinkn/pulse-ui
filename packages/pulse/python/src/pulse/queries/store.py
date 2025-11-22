from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

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
		if key in self._entries:
			return self._entries[key]

		def _on_dispose(e: Query[Any]) -> None:
			print("disposing query entry in store", e.key)
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
