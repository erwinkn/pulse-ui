import datetime as dt
from collections.abc import Callable
from typing import Any, TypeVar, cast

from pulse.helpers import MISSING
from pulse.queries.common import QueryKey
from pulse.queries.infinite_query import InfiniteQuery, Page
from pulse.queries.query import RETRY_DELAY_DEFAULT, KeyedQuery

T = TypeVar("T")


class QueryStore:
	"""
	Store for query entries. Manages creation, retrieval, and disposal of queries.
	"""

	def __init__(self):
		self._entries: dict[QueryKey, KeyedQuery[Any] | InfiniteQuery[Any, Any]] = {}

	def items(self):
		"""Iterate over all (key, query) pairs in the store."""
		return self._entries.items()

	def get_any(self, key: QueryKey):
		"""Get any query (regular or infinite) by key, or None if not found."""
		return self._entries.get(key)

	def ensure(
		self,
		key: QueryKey,
		initial_data: T | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
	) -> KeyedQuery[T]:
		# Return existing entry if present
		existing = self._entries.get(key)
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
			key,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			retries=retries,
			retry_delay=retry_delay,
			on_dispose=_on_dispose,
		)
		self._entries[key] = entry
		return entry

	def get(self, key: QueryKey) -> KeyedQuery[Any] | None:
		"""
		Get an existing regular query by key, or None if not found.
		"""
		existing = self._entries.get(key)
		if existing and isinstance(existing, InfiniteQuery):
			return None
		return existing

	def get_infinite(self, key: QueryKey) -> InfiniteQuery[Any, Any] | None:
		"""
		Get an existing infinite query by key, or None if not found.
		"""
		existing = self._entries.get(key)
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
		initial_data: list[Page[Any, Any]] | None | Any = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
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
		self._entries[key] = entry
		return entry
