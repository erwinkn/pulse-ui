import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import (
	Any,
	Generic,
	Literal,
	TypeAlias,
	TypeVar,
	cast,
	override,
)

from pulse.helpers import is_running_under_pytest, later
from pulse.reactive import AsyncEffect, Computed, Signal

T = TypeVar("T")
QueryKey: TypeAlias = tuple[Hashable, ...]
QueryStatus: TypeAlias = Literal["loading", "success", "error"]
QueryFetchStatus: TypeAlias = Literal["idle", "fetching", "paused"]


class AsyncQueryEffect(AsyncEffect):
	"""
	Specialized AsyncEffect for queries that synchronously sets loading state
	when rescheduled/run.
	"""

	query: "Query[Any]"

	def __init__(
		self,
		fn: Callable[[], Awaitable[None]],
		query: "Query[Any]",
		name: str | None = None,
		lazy: bool = False,
		deps: list[Signal[Any] | Computed[Any]] | None = None,
	):
		self.query = query
		super().__init__(fn, name=name, lazy=lazy, deps=deps)

	@override
	def run(self) -> asyncio.Task[Any]:
		# Immediately set loading state before running the effect
		self.query.fetch_status.write("fetching")
		return super().run()


@dataclass(slots=True)
class QueryConfig(Generic[T]):
	retries: int
	retry_delay: float
	initial_data: T | Callable[[], T] | None
	gc_time: float
	on_dispose: Callable[[Any], None] | None


RETRY_DELAY_DEFAULT = 2.0 if not is_running_under_pytest() else 0.01


class Query(Generic[T]):
	"""
	Represents a single query instance in a store.
	Manages the async effect, data/status signals, and observer tracking.
	"""

	key: QueryKey | None
	fn: Callable[[], Awaitable[T]]
	cfg: QueryConfig[T]

	# Reactive signals for query state
	data: Signal[T | None]
	error: Signal[Exception | None]
	last_updated: Signal[float]
	status: Signal[QueryStatus]
	fetch_status: Signal[QueryFetchStatus]
	retries: Signal[int]
	retry_reason: Signal[Exception | None]

	_obs_count: int
	_effect: AsyncEffect | None
	_gc_handle: asyncio.TimerHandle | None

	def __init__(
		self,
		key: QueryKey | None,
		fn: Callable[[], Awaitable[T]],
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: T | None = None,
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.key = key
		self.fn = fn
		self.cfg = QueryConfig(
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			gc_time=gc_time,
			on_dispose=on_dispose,
		)

		# Initialize reactive signals
		self.data = Signal(initial_data, name=f"query.data({key})")
		self.error = Signal(None, name=f"query.error({key})")
		self.last_updated = Signal(
			time.time() if initial_data else 0.0, name=f"query.last_updated({key})"
		)
		self.status = Signal(
			"loading" if initial_data is None else "success",
			name=f"query.status({key})",
		)
		self.fetch_status = Signal("idle", name=f"query.fetch_status({key})")
		self.retries = Signal(0, name=f"query.retries({key})")
		self.retry_reason = Signal(None, name=f"query.retry_reason({key})")

		self._obs_count = 0
		self._gc_handle = None
		# Effect is created lazily on first observation
		self._effect = None
		# Schedule GC, will be cancelled by first observer
		self.schedule_gc()

	def set_data(self, data: T):
		self._set_success(data, manual=True)

	def set_error(self, error: Exception):
		self._set_error(error, manual=True)

	def _set_success(self, data: T, manual: bool = False):
		self.data.write(data)
		self.last_updated.write(time.time())
		self.error.write(None)
		self.status.write("success")
		if not manual:
			self.fetch_status.write("idle")
			self.retries.write(0)
			self.retry_reason.write(None)

	def _set_error(self, error: Exception, manual: bool = False):
		self.error.write(error)
		self.last_updated.write(time.time())
		self.status.write("error")
		if not manual:
			self.fetch_status.write("idle")
			# Don't reset retries on final error - preserve for debugging
			# retry_reason is updated to the final error in _run

	def _failed_retry(self, reason: Exception):
		self.retries.write(self.retries.read() + 1)
		self.retry_reason.write(reason)

	@property
	def effect(self) -> AsyncEffect:
		"""Lazy property that creates the query effect on first access."""
		if self._effect is None:
			self._effect = AsyncQueryEffect(
				self._run,
				query=self,
				name=f"query_effect({self.key})",
				lazy=True,
				deps=[] if self.key is not None else None,
			)
		return self._effect

	async def _run(self):
		# Reset retries at start of run
		self.retries.write(0)
		self.retry_reason.write(None)

		while True:
			try:
				result = await self.fn()
				self._set_success(result)
				return
			except asyncio.CancelledError:
				raise
			except Exception as e:
				current_retries = self.retries.read()
				if current_retries < self.cfg.retries:
					# Record failed retry attempt and retry
					self._failed_retry(e)
					# Wait before retrying
					await asyncio.sleep(self.cfg.retry_delay)
				else:
					# All retries exhausted - update retry_reason to final error
					self.retry_reason.write(e)
					self._set_error(e)
					return

	async def refetch(self, cancel_refetch: bool = True) -> T:
		"""
		Reruns the query and returns the result.
		If cancel_refetch is True (default), cancels any in-flight request and starts a new one.
		If cancel_refetch is False, deduplicates requests if one is already in flight.
		"""
		if cancel_refetch:
			self.effect.cancel()
		return await self.wait()

	async def wait(self) -> T:
		await self.effect.wait()
		return cast(T, self.data.read())

	def invalidate(self, cancel_refetch: bool = False):
		"""
		Marks query as stale. If there are active observers, triggers a refetch.
		"""
		should_schedule = not self.effect.is_scheduled or cancel_refetch
		if should_schedule and self._obs_count > 0:
			self.effect.schedule()

	def observe(self, gc_time: float = 300.0):
		"""Register an observer. Cancels GC and updates gc_time if provided."""
		# Access effect to ensure it's created (lazy property)
		_ = self.effect
		self._obs_count += 1
		self.cancel_gc()
		if gc_time > 0:
			self.cfg.gc_time = max(self.cfg.gc_time, gc_time)

	def unobserve(self):
		"""Unregister an observer. Schedules GC if no observers remain."""
		self._obs_count -= 1
		if self._obs_count == 0:
			self.schedule_gc()

	def schedule_gc(self):
		self.cancel_gc()
		if self.cfg.gc_time > 0:
			self._gc_handle = later(self.cfg.gc_time, self.dispose)
		else:
			self.dispose()

	def cancel_gc(self):
		if self._gc_handle:
			self._gc_handle.cancel()
			self._gc_handle = None

	def dispose(self):
		"""
		Cleans up the query entry, removing it from the store.
		"""
		if self._effect:
			self._effect.dispose()

		if self.cfg.on_dispose:
			self.cfg.on_dispose(self)
