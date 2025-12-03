import datetime as dt
from collections.abc import Callable
from typing import Protocol, TypeVar, runtime_checkable

from pulse.queries.common import ActionResult, QueryStatus

T = TypeVar("T")


@runtime_checkable
class QueryResult(Protocol[T]):
	"""
	Unified query result interface for both keyed and unkeyed queries.

	This protocol defines the public API that all query results expose,
	regardless of whether they use keyed (cached/shared) or unkeyed
	(dependency-tracked) execution strategies.

	Keyed queries use a session-wide cache and explicit key functions to
	determine when to refetch. Unkeyed queries automatically track reactive
	dependencies and refetch when those dependencies change.
	"""

	# Status properties
	@property
	def status(self) -> QueryStatus:
		"""Current query status: 'loading', 'success', or 'error'."""
		...

	@property
	def is_loading(self) -> bool:
		"""True if the query has not yet completed its initial fetch."""
		...

	@property
	def is_success(self) -> bool:
		"""True if the query completed successfully."""
		...

	@property
	def is_error(self) -> bool:
		"""True if the query completed with an error."""
		...

	@property
	def is_fetching(self) -> bool:
		"""True if a fetch is currently in progress (including refetches)."""
		...

	@property
	def is_scheduled(self) -> bool:
		"""True if a fetch is scheduled or currently running."""
		...

	# Data properties
	@property
	def data(self) -> T | None:
		"""The query result data, or None if not yet available."""
		...

	@property
	def error(self) -> Exception | None:
		"""The error from the last fetch, or None if no error."""
		...

	# Query operations
	def is_stale(self) -> bool:
		"""Check if the query data is stale based on stale_time."""
		...

	async def refetch(self, cancel_refetch: bool = True) -> ActionResult[T]:
		"""
		Refetch the query data.

		Args:
		    cancel_refetch: If True (default), cancels any in-flight request
		        before starting a new one. If False, deduplicates requests.

		Returns:
		    ActionResult containing either the data or an error.
		"""
		...

	async def wait(self) -> ActionResult[T]:
		"""
		Wait for the current fetch to complete.

		Returns:
		    ActionResult containing either the data or an error.
		"""
		...

	def invalidate(self) -> None:
		"""Mark the query as stale and trigger a refetch if observed."""
		...

	# Data manipulation
	def set_data(self, data: T | Callable[[T | None], T]) -> None:
		"""
		Optimistically set data without changing loading/error state.

		Args:
		    data: The new data value, or a function that receives the current
		        data and returns the new data.
		"""
		...

	def set_initial_data(
		self,
		data: T | Callable[[], T],
		*,
		updated_at: float | dt.datetime | None = None,
	) -> None:
		"""
		Set data as if it were provided as initial_data.

		Only takes effect if the query is still in 'loading' state.

		Args:
		    data: The initial data value, or a function that returns it.
		    updated_at: Optional timestamp to seed staleness calculations.
		"""
		...

	def set_error(self, error: Exception) -> None:
		"""Set error state on the query."""
		...

	# Enable/disable
	def enable(self) -> None:
		"""Enable the query, allowing it to fetch."""
		...

	def disable(self) -> None:
		"""Disable the query, preventing it from fetching."""
		...
