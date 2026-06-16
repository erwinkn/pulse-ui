import datetime as dt
from collections.abc import Callable
from typing import Any, TypeVar, cast, override

from pulse.helpers import MISSING, Disposable, Missing
from pulse.queries.common import Key, QueryKey, normalize_key
from pulse.queries.infinite_query import InfiniteQuery, Page
from pulse.queries.query import RETRY_DELAY_DEFAULT, KeyedQuery, UnkeyedQueryResult

T = TypeVar("T")


class QueryStore(Disposable):
	"""
	Store for query entries. Manages creation, retrieval, and disposal of queries.

	Also tracks the session's connection state: while suspended (client
	disconnected), interval refetching is paused; on resume, intervals restart
	and stale queries refetch.
	"""

	suspended: bool

	def __init__(self):
		self._entries: dict[Key, KeyedQuery[Any] | InfiniteQuery[Any, Any]] = {}
		self._unkeyed: set[UnkeyedQueryResult[Any]] = set()
		self.suspended = False

	def register_unkeyed(self, result: UnkeyedQueryResult[Any]) -> None:
		"""Track an unkeyed query result so it participates in suspend/resume."""
		self._unkeyed.add(result)
		if self.suspended:
			result.suspend()

	def unregister_unkeyed(self, result: UnkeyedQueryResult[Any]) -> None:
		self._unkeyed.discard(result)

	def suspend_all(self) -> None:
		"""Pause interval refetching for all queries (client disconnected)."""
		if self.suspended:
			return
		self.suspended = True
		for entry in self._entries.values():
			entry.suspend()
		for result in self._unkeyed:
			result.suspend()

	def resume_all(self) -> None:
		"""Restart intervals and refetch stale queries (client reconnected)."""
		if not self.suspended:
			return
		self.suspended = False
		for entry in list(self._entries.values()):
			entry.resume()
		for result in list(self._unkeyed):
			result.resume()

	def items(self):
		"""Iterate over all (key, query) pairs in the store."""
		return self._entries.items()

	def get_any(self, key: QueryKey):
		"""Get any query (regular or infinite) by key, or None if not found."""
		return self._entries.get(normalize_key(key))

	def ensure(
		self,
		key: QueryKey,
		initial_data: T | Missing | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
	) -> KeyedQuery[T]:
		nkey = normalize_key(key)
		# Return existing entry if present
		existing = self._entries.get(nkey)
		if existing:
			if isinstance(existing, InfiniteQuery):
				raise TypeError(
					"Query key is already used for an infinite query; cannot reuse for regular query"
				)
			return cast(KeyedQuery[T], existing)

		def _on_dispose(e: KeyedQuery[Any]) -> None:
			if e.key in self._entries and self._entries[e.key] is e:
				del self._entries[e.key]

		entry = KeyedQuery(
			nkey,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			retries=retries,
			retry_delay=retry_delay,
			on_dispose=_on_dispose,
		)
		if self.suspended:
			entry.suspend()
		self._entries[nkey] = entry
		return entry

	def get(self, key: QueryKey) -> KeyedQuery[Any] | None:
		"""
		Get an existing regular query by key, or None if not found.
		"""
		existing = self._entries.get(normalize_key(key))
		if existing and isinstance(existing, InfiniteQuery):
			return None
		return existing

	def get_infinite(self, key: QueryKey) -> InfiniteQuery[Any, Any] | None:
		"""
		Get an existing infinite query by key, or None if not found.
		"""
		existing = self._entries.get(normalize_key(key))
		if existing and isinstance(existing, InfiniteQuery):
			return existing
		return None

	def ensure_infinite(
		self,
		key: QueryKey,
		*,
		initial_page_param: Any,
		get_next_page_param: Callable[[list[Page[Any, Any]]], Any | None],
		get_previous_page_param: Callable[[list[Page[Any, Any]]], Any | None]
		| None = None,
		max_pages: int = 0,
		initial_data: list[Page[Any, Any]] | Missing | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
	) -> InfiniteQuery[Any, Any]:
		nkey = normalize_key(key)
		existing = self._entries.get(nkey)
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
			nkey,
			initial_page_param=initial_page_param,
			get_next_page_param=get_next_page_param,
			get_previous_page_param=get_previous_page_param,
			max_pages=max_pages,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			retries=retries,
			retry_delay=retry_delay,
			on_dispose=_on_dispose,
		)
		if self.suspended:
			entry.suspend()
		self._entries[nkey] = entry
		return entry

	def dispose_all(self) -> None:
		"""Dispose all queries and clear the store."""
		for entry in list(self._entries.values()):
			entry.dispose()
		self._entries.clear()
		# Unkeyed results are owned and disposed by their States; just drop refs
		self._unkeyed.clear()

	@override
	def dispose(self) -> None:
		self.dispose_all()
