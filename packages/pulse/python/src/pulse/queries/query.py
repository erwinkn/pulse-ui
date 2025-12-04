import asyncio
import datetime as dt
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
	TYPE_CHECKING,
	Any,
	Generic,
	TypeVar,
	cast,
	overload,
	override,
)

from pulse.context import PulseContext
from pulse.helpers import (
	MISSING,
	Disposable,
	call_flexible,
	is_pytest,
	later,
	maybe_await,
)
from pulse.queries.common import (
	ActionError,
	ActionResult,
	ActionSuccess,
	OnErrorFn,
	OnSuccessFn,
	QueryKey,
	QueryStatus,
	bind_state,
)
from pulse.queries.effect import AsyncQueryEffect
from pulse.reactive import Computed, Effect, Signal, Untrack
from pulse.state import InitializableProperty, State

if TYPE_CHECKING:
	from pulse.queries.protocol import QueryResult

T = TypeVar("T")
TState = TypeVar("TState", bound=State)

RETRY_DELAY_DEFAULT = 2.0 if not is_pytest() else 0.01


@dataclass(slots=True)
class QueryConfig(Generic[T]):
	retries: int
	retry_delay: float
	initial_data: T | Callable[[], T] | None
	initial_data_updated_at: float | dt.datetime | None
	gc_time: float
	on_dispose: Callable[[Any], None] | None


class QueryState(Generic[T]):
	"""
	Container for query state signals and manipulation methods.
	Used by both KeyedQuery and UnkeyedQuery via composition.
	"""

	cfg: QueryConfig[T]

	# Reactive signals for query state
	data: Signal[T | None]
	error: Signal[Exception | None]
	last_updated: Signal[float]
	status: Signal[QueryStatus]
	is_fetching: Signal[bool]
	retries: Signal[int]
	retry_reason: Signal[Exception | None]

	def __init__(
		self,
		name: str,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: T | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.cfg = QueryConfig(
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			on_dispose=on_dispose,
		)

		# Initialize reactive signals
		self.data = Signal(
			None if initial_data is MISSING else initial_data,
			name=f"query.data({name})",
		)
		self.error = Signal(None, name=f"query.error({name})")

		self.last_updated = Signal(
			0.0,
			name=f"query.last_updated({name})",
		)
		if initial_data_updated_at:
			self.set_updated_at(initial_data_updated_at)

		self.status = Signal(
			"loading" if initial_data is MISSING else "success",
			name=f"query.status({name})",
		)
		self.is_fetching = Signal(False, name=f"query.is_fetching({name})")
		self.retries = Signal(0, name=f"query.retries({name})")
		self.retry_reason = Signal(None, name=f"query.retry_reason({name})")

	def set_data(
		self,
		data: T | Callable[[T | None], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		"""Set data manually, accepting a value or updater function."""
		current = self.data.read()
		new_value = cast(T, data(current) if callable(data) else data)
		self.set_success(new_value, manual=True)
		if updated_at is not None:
			self.set_updated_at(updated_at)

	def set_updated_at(self, updated_at: float | dt.datetime):
		if isinstance(updated_at, dt.datetime):
			updated_at = updated_at.timestamp()
		self.last_updated.write(updated_at)

	def set_initial_data(
		self,
		data: T | Callable[[], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		"""
		Set data as if it were provided as initial_data.
		Optionally supply an updated_at timestamp to seed staleness calculations.
		"""
		if self.status() == "loading":
			value = cast(T, data() if callable(data) else data)
			self.set_data(value, updated_at=updated_at)

	def set_error(
		self, error: Exception, *, updated_at: float | dt.datetime | None = None
	):
		self.apply_error(error, manual=True)
		if updated_at is not None:
			self.set_updated_at(updated_at)

	def set_success(self, data: T, manual: bool = False):
		"""Set success state with data."""
		self.data.write(data)
		self.last_updated.write(time.time())
		self.error.write(None)
		self.status.write("success")
		if not manual:
			self.is_fetching.write(False)
			self.retries.write(0)
			self.retry_reason.write(None)

	def apply_error(self, error: Exception, manual: bool = False):
		"""Apply error state to the query."""
		self.error.write(error)
		self.last_updated.write(time.time())
		self.status.write("error")
		if not manual:
			self.is_fetching.write(False)
			# Don't reset retries on final error - preserve for debugging

	def failed_retry(self, reason: Exception):
		"""Record a failed retry attempt."""
		self.retries.write(self.retries.read() + 1)
		self.retry_reason.write(reason)

	def reset_retries(self):
		"""Reset retry state at start of fetch."""
		self.retries.write(0)
		self.retry_reason.write(None)


async def run_fetch_with_retries(
	state: QueryState[T],
	fetch_fn: Callable[[], Awaitable[T]],
	on_success: Callable[[T], Awaitable[None] | None] | None = None,
	on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
	untrack: bool = False,
) -> None:
	"""
	Execute a fetch with retry logic, updating QueryState.

	Args:
		state: The QueryState to update
		fetch_fn: Async function to fetch data
		on_success: Optional callback on success
		on_error: Optional callback on error
		untrack: If True, wrap fetch_fn in Untrack() to prevent dependency tracking.
		         Use for keyed queries where fetch is triggered via asyncio.create_task.
	"""
	state.reset_retries()

	while True:
		try:
			if untrack:
				with Untrack():
					result = await fetch_fn()
			else:
				result = await fetch_fn()
			state.set_success(result)
			if on_success:
				await maybe_await(call_flexible(on_success, result))
			return
		except asyncio.CancelledError:
			raise
		except Exception as e:
			current_retries = state.retries.read()
			if current_retries < state.cfg.retries:
				state.failed_retry(e)
				await asyncio.sleep(state.cfg.retry_delay)
			else:
				state.retry_reason.write(e)
				state.apply_error(e)
				if on_error:
					await maybe_await(call_flexible(on_error, e))
				return


class KeyedQuery(Generic[T], Disposable):
	"""
	Query for keyed queries (shared across observers).
	Uses direct task management without dependency tracking.
	Multiple observers can share the same query.
	"""

	key: QueryKey
	state: QueryState[T]
	observers: "list[KeyedQueryResult[T]]"
	_task: asyncio.Task[None] | None
	_task_initiator: "KeyedQueryResult[T] | None"
	_gc_handle: asyncio.TimerHandle | None

	def __init__(
		self,
		key: QueryKey,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: T | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.key = key
		self.state = QueryState(
			name=str(key),
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			on_dispose=on_dispose,
		)
		self.observers = []
		self._task = None
		self._task_initiator = None
		self._gc_handle = None

	# --- Delegate signal access to state ---
	@property
	def data(self) -> Signal[T | None]:
		return self.state.data

	@property
	def error(self) -> Signal[Exception | None]:
		return self.state.error

	@property
	def last_updated(self) -> Signal[float]:
		return self.state.last_updated

	@property
	def status(self) -> Signal[QueryStatus]:
		return self.state.status

	@property
	def is_fetching(self) -> Signal[bool]:
		return self.state.is_fetching

	@property
	def retries(self) -> Signal[int]:
		return self.state.retries

	@property
	def retry_reason(self) -> Signal[Exception | None]:
		return self.state.retry_reason

	@property
	def cfg(self) -> QueryConfig[T]:
		return self.state.cfg

	# --- Delegate state methods ---
	def set_data(
		self,
		data: T | Callable[[T | None], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		self.state.set_data(data, updated_at=updated_at)

	def set_initial_data(
		self,
		data: T | Callable[[], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		self.state.set_initial_data(data, updated_at=updated_at)

	def set_error(
		self, error: Exception, *, updated_at: float | dt.datetime | None = None
	):
		self.state.set_error(error, updated_at=updated_at)

	# --- Query-specific methods ---
	@property
	def is_scheduled(self) -> bool:
		"""Check if a fetch is currently scheduled/running."""
		return self._task is not None and not self._task.done()

	async def _run_fetch(
		self,
		fetch_fn: Callable[[], Awaitable[T]],
		observers: "list[KeyedQueryResult[T]]",
	) -> None:
		"""Execute the fetch with retry logic."""

		async def on_success(result: T):
			for obs in observers:
				if obs._on_success:  # pyright: ignore[reportPrivateUsage]
					await maybe_await(call_flexible(obs._on_success, result))  # pyright: ignore[reportPrivateUsage]

		async def on_error(e: Exception):
			for obs in observers:
				if obs._on_error:  # pyright: ignore[reportPrivateUsage]
					await maybe_await(call_flexible(obs._on_error, e))  # pyright: ignore[reportPrivateUsage]

		await run_fetch_with_retries(
			self.state,
			fetch_fn,
			on_success=on_success,
			on_error=on_error,
			untrack=True,  # Keyed queries use asyncio.create_task, need to untrack
		)

	def run_fetch(
		self,
		fetch_fn: Callable[[], Awaitable[T]],
		cancel_previous: bool = True,
		initiator: "KeyedQueryResult[T] | None" = None,
	) -> asyncio.Task[None]:
		"""
		Start a fetch with the given fetch function.
		Cancels any in-flight fetch if cancel_previous is True.

		Args:
			fetch_fn: The async function to fetch data.
			cancel_previous: If True, cancels any in-flight fetch before starting.
			initiator: The KeyedQueryResult observer that initiated this fetch (for cancellation tracking).
		"""
		if cancel_previous and self._task and not self._task.done():
			self._task.cancel()

		self.state.is_fetching.write(True)
		# Capture current observers at fetch start
		observers = list(self.observers)
		self._task = asyncio.create_task(self._run_fetch(fetch_fn, observers))
		self._task_initiator = initiator
		return self._task

	async def wait(self) -> ActionResult[T]:
		"""Wait for the current fetch to complete."""
		while self._task and not self._task.done():
			try:
				await self._task
			except asyncio.CancelledError:
				# Task was cancelled (probably by a new refetch).
				# If there's a new task, wait for that one instead.
				# If no new task, re-raise the cancellation.
				# Note: self._task may have been reassigned by run_fetch() after await
				if self._task is None or self._task.done():  # pyright: ignore[reportUnnecessaryComparison]
					raise
				# Otherwise, loop and wait for the new task
		# Return result based on current state
		if self.state.status() == "error":
			return ActionError(cast(Exception, self.state.error.read()))
		return ActionSuccess(cast(T, self.state.data.read()))

	def cancel(self) -> None:
		"""Cancel the current fetch if running."""
		if self._task and not self._task.done():
			self._task.cancel()
			self._task = None
			self._task_initiator = None

	def _get_first_observer_fetch_fn(self) -> Callable[[], Awaitable[T]]:
		"""Get the fetch function from the first observer."""
		if len(self.observers) == 0:
			raise RuntimeError(
				f"Query '{self.key}' has no observers. Cannot access fetch function."
			)
		return self.observers[0]._fetch_fn  # pyright: ignore[reportPrivateUsage]

	async def refetch(self, cancel_refetch: bool = True) -> ActionResult[T]:
		"""
		Reruns the query and returns the result.
		Uses the first observer's fetch function.

		Note: Prefer calling refetch() on KeyedQueryResult to ensure the correct fetch function is used.
		"""
		fetch_fn = self._get_first_observer_fetch_fn()
		if cancel_refetch or not self.is_fetching():
			self.run_fetch(fetch_fn, cancel_previous=cancel_refetch)
		return await self.wait()

	def invalidate(self, cancel_refetch: bool = False):
		"""
		Marks query as stale. If there are active observers, triggers a refetch.
		Uses the first observer's fetch function.

		Note: Prefer calling invalidate() on KeyedQueryResult to ensure the correct fetch function is used.
		"""
		if len(self.observers) > 0:
			fetch_fn = self._get_first_observer_fetch_fn()
			if not self.is_scheduled or cancel_refetch:
				self.run_fetch(fetch_fn, cancel_previous=cancel_refetch)

	def observe(self, observer: "KeyedQueryResult[T]"):
		"""Register an observer."""
		self.observers.append(observer)
		self.cancel_gc()
		if observer._gc_time > 0:  # pyright: ignore[reportPrivateUsage]
			self.cfg.gc_time = max(self.cfg.gc_time, observer._gc_time)  # pyright: ignore[reportPrivateUsage]

	def unobserve(self, observer: "KeyedQueryResult[T]"):
		"""Unregister an observer. Schedules GC if no observers remain."""
		if observer in self.observers:
			self.observers.remove(observer)

		# If the departing observer initiated the ongoing fetch, cancel it
		if self._task_initiator is observer and self._task and not self._task.done():
			self._task.cancel()
			self._task = None
			self._task_initiator = None
			# Reschedule from another observer if any remain
			if len(self.observers) > 0:
				fetch_fn = self._get_first_observer_fetch_fn()
				self.run_fetch(
					fetch_fn, cancel_previous=False, initiator=self.observers[0]
				)

		if len(self.observers) == 0:
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

	@override
	def dispose(self):
		"""Clean up the query, cancelling any in-flight fetch."""
		self.cancel()
		if self.cfg.on_dispose:
			self.cfg.on_dispose(self)


class UnkeyedQueryResult(Generic[T], Disposable):
	"""
	Query for unkeyed queries (single observer with dependency tracking).
	Uses an AsyncEffect to track dependencies and re-run on changes.

	Unlike KeyedQuery which separates the query from its observer (KeyedQueryResult),
	UnkeyedQuery combines both since there's always exactly one observer.
	"""

	state: QueryState[T]
	_effect: AsyncQueryEffect
	_fetch_fn: Callable[[], Awaitable[T]]
	_on_success: Callable[[T], Awaitable[None] | None] | None
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_stale_time: float
	_refetch_interval: float | None
	_keep_previous_data: bool
	_enabled: Signal[bool]
	_interval_effect: Effect | None
	_data_computed: Computed[T | None]

	def __init__(
		self,
		fetch_fn: Callable[[], Awaitable[T]],
		on_success: Callable[[T], Awaitable[None] | None] | None = None,
		on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: T | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		stale_time: float = 0.0,
		refetch_interval: float | None = None,
		keep_previous_data: bool = False,
		enabled: bool = True,
		fetch_on_mount: bool = True,
	):
		self.state = QueryState(
			name="unkeyed",
			retries=retries,
			retry_delay=retry_delay,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=gc_time,
			on_dispose=None,
		)
		self._fetch_fn = fetch_fn
		self._on_success = on_success
		self._on_error = on_error
		self._stale_time = stale_time
		self._refetch_interval = refetch_interval
		self._keep_previous_data = keep_previous_data
		self._enabled = Signal(enabled, name="query.enabled(unkeyed)")
		self._interval_effect = None

		# Create effect with auto-tracking (deps=None)
		# Pass state as fetcher since it has the Signal attributes directly
		self._effect = AsyncQueryEffect(
			self._run,
			fetcher=self.state,
			name="unkeyed_query_effect",
			deps=None,  # Auto-track dependencies
			lazy=True,
		)

		# Computed for keep_previous_data logic
		self._data_computed = Computed(
			self._data_computed_fn, name="query_data(unkeyed)"
		)

		# Schedule initial fetch if stale (untracked to avoid reactive loop)
		with Untrack():
			if enabled and fetch_on_mount and self.is_stale():
				self.schedule()

		# Set up interval effect if interval is specified
		if refetch_interval is not None and refetch_interval > 0:
			self._setup_interval_effect(refetch_interval)

	def _setup_interval_effect(self, interval: float):
		"""Create an effect that invalidates the query at the specified interval."""

		def interval_fn():
			if self._enabled():
				self.schedule()

		self._interval_effect = Effect(
			interval_fn,
			name="query_interval(unkeyed)",
			interval=interval,
			immediate=True,
		)

	def _data_computed_fn(self, prev: T | None) -> T | None:
		if self._keep_previous_data and self.state.status() != "success":
			return prev
		raw = self.state.data()
		if raw is None:
			return None
		return raw

	# --- Status properties ---
	@property
	def status(self) -> QueryStatus:
		return self.state.status()

	@property
	def is_loading(self) -> bool:
		return self.status == "loading"

	@property
	def is_success(self) -> bool:
		return self.status == "success"

	@property
	def is_error(self) -> bool:
		return self.status == "error"

	@property
	def is_fetching(self) -> bool:
		return self.state.is_fetching()

	@property
	def error(self) -> Exception | None:
		return self.state.error.read()

	@property
	def data(self) -> T | None:
		return self._data_computed()

	# --- State methods ---
	def set_data(self, data: T | Callable[[T | None], T]):
		"""Optimistically set data without changing loading/error state."""
		self.state.set_data(data)

	def set_initial_data(
		self,
		data: T | Callable[[], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		"""Seed initial data and optional freshness timestamp."""
		self.state.set_initial_data(data, updated_at=updated_at)

	def set_error(self, error: Exception):
		"""Set error state on the query."""
		self.state.set_error(error)

	def enable(self):
		"""Enable the query."""
		self._enabled.write(True)

	def disable(self):
		"""Disable the query, preventing it from fetching."""
		self._enabled.write(False)

	# --- Query operations ---
	def is_stale(self) -> bool:
		"""Check if the query data is stale based on stale_time."""
		return (time.time() - self.state.last_updated.read()) > self._stale_time

	async def _run(self):
		"""Run the fetch through the effect (for dependency tracking)."""
		# Unkeyed queries run inside AsyncEffect which has its own scope,
		# so we don't need untrack=True here - deps should be tracked
		await run_fetch_with_retries(
			self.state,
			self._fetch_fn,
			on_success=self._on_success,
			on_error=self._on_error,
			untrack=False,
		)

	def schedule(self):
		"""Schedule the effect to run."""
		self._effect.schedule()

	@property
	def is_scheduled(self) -> bool:
		"""Check if a fetch is currently scheduled/running."""
		return self._effect.is_scheduled

	async def refetch(self, cancel_refetch: bool = True) -> ActionResult[T]:
		"""Refetch the query data through the effect."""
		if cancel_refetch:
			self.cancel()
		self.schedule()
		return await self.wait()

	async def wait(self) -> ActionResult[T]:
		"""Wait for the current query to complete."""
		# If loading and no task, schedule a fetch
		if self.state.status() == "loading" and not self.state.is_fetching():
			self.schedule()
		await self._effect.wait()
		if self.state.status() == "error":
			return ActionError(cast(Exception, self.state.error.read()))
		return ActionSuccess(cast(T, self.state.data.read()))

	def invalidate(self):
		"""Mark the query as stale and refetch through the effect."""
		if not self.is_scheduled:
			self.schedule()

	def cancel(self) -> None:
		"""Cancel the current fetch if running."""
		self._effect.cancel(cancel_interval=False)

	@override
	def dispose(self):
		"""Clean up the query and its effect."""
		if self._interval_effect is not None:
			self._interval_effect.dispose()
		self._effect.dispose()


class KeyedQueryResult(Generic[T], Disposable):
	"""
	Observer wrapper for keyed queries.
	Handles observation lifecycle, staleness tracking, and provides query operations.
	"""

	_query: Computed[KeyedQuery[T]]
	_fetch_fn: Callable[[], Awaitable[T]]
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_keep_previous_data: bool
	_on_success: Callable[[T], Awaitable[None] | None] | None
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_observe_effect: Effect
	_interval_effect: Effect | None
	_data_computed: Computed[T | None]
	_enabled: Signal[bool]
	_fetch_on_mount: bool

	def __init__(
		self,
		query: Computed[KeyedQuery[T]],
		fetch_fn: Callable[[], Awaitable[T]],
		stale_time: float = 0.0,
		gc_time: float = 300.0,
		refetch_interval: float | None = None,
		keep_previous_data: bool = False,
		on_success: Callable[[T], Awaitable[None] | None] | None = None,
		on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
		enabled: bool = True,
		fetch_on_mount: bool = True,
	):
		self._query = query
		self._fetch_fn = fetch_fn
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._refetch_interval = refetch_interval
		self._keep_previous_data = keep_previous_data
		self._on_success = on_success
		self._on_error = on_error
		self._enabled = Signal(enabled, name=f"query.enabled({query().key})")
		self._interval_effect = None

		def observe_effect():
			q = self._query()
			enabled = self._enabled()

			with Untrack():
				q.observe(self)

				# If stale or loading, schedule refetch (only when enabled)
				if enabled and fetch_on_mount and self.is_stale():
					self.invalidate()

			# Return cleanup function that captures the query (old query on key change)
			def cleanup():
				q.unobserve(self)

			return cleanup

		self._observe_effect = Effect(
			observe_effect,
			name=f"query_observe({self._query().key})",
			immediate=True,
		)
		self._data_computed = Computed(
			self._data_computed_fn, name=f"query_data({self._query().key})"
		)

		# Set up interval effect if interval is specified
		if refetch_interval is not None and refetch_interval > 0:
			self._setup_interval_effect(refetch_interval)

	def _setup_interval_effect(self, interval: float):
		"""Create an effect that invalidates the query at the specified interval."""

		def interval_fn():
			# Read enabled to make this effect reactive to enabled changes
			if self._enabled():
				self.invalidate()

		self._interval_effect = Effect(
			interval_fn,
			name=f"query_interval({self._query().key})",
			interval=interval,
			immediate=True,
		)

	@property
	def status(self) -> QueryStatus:
		return self._query().status()

	@property
	def is_loading(self) -> bool:
		return self.status == "loading"

	@property
	def is_success(self) -> bool:
		return self.status == "success"

	@property
	def is_error(self) -> bool:
		return self.status == "error"

	@property
	def is_fetching(self) -> bool:
		return self._query().is_fetching()

	@property
	def is_scheduled(self) -> bool:
		return self._query().is_scheduled

	@property
	def error(self) -> Exception | None:
		return self._query().error.read()

	def _data_computed_fn(self, prev: T | None) -> T | None:
		query = self._query()
		if self._keep_previous_data and query.status() != "success":
			return prev
		raw = query.data()
		if raw is None:
			return None
		return raw

	@property
	def data(self) -> T | None:
		return self._data_computed()

	def is_stale(self) -> bool:
		"""Check if the query data is stale based on stale_time."""
		query = self._query()
		return (time.time() - query.last_updated.read()) > self._stale_time

	async def refetch(self, cancel_refetch: bool = True) -> ActionResult[T]:
		"""
		Refetch the query data using this observer's fetch function.
		If cancel_refetch is True (default), cancels any in-flight request and starts a new one.
		If cancel_refetch is False, deduplicates requests if one is already in flight.
		"""
		query = self._query()
		if cancel_refetch or not query.is_fetching():
			query.run_fetch(
				self._fetch_fn, cancel_previous=cancel_refetch, initiator=self
			)
		return await self.wait()

	async def wait(self) -> ActionResult[T]:
		"""Wait for the current query to complete."""
		query = self._query()
		# If loading and no task, start a fetch with this observer's fetch function
		if query.status() == "loading" and not query.is_fetching():
			query.run_fetch(self._fetch_fn, initiator=self)
		return await query.wait()

	def invalidate(self):
		"""Mark the query as stale and refetch using this observer's fetch function."""
		query = self._query()
		if not query.is_scheduled and len(query.observers) > 0:
			query.run_fetch(self._fetch_fn, cancel_previous=False, initiator=self)

	def set_data(self, data: T | Callable[[T | None], T]):
		"""Optimistically set data without changing loading/error state."""
		query = self._query()
		query.set_data(data)

	def set_initial_data(
		self,
		data: T | Callable[[], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		"""Seed initial data and optional freshness timestamp."""
		query = self._query()
		query.set_initial_data(data, updated_at=updated_at)

	def set_error(self, error: Exception):
		"""Set error state on the query."""
		query = self._query()
		query.set_error(error)

	def enable(self):
		"""Enable the query."""
		self._enabled.write(True)

	def disable(self):
		"""Disable the query, preventing it from fetching."""
		self._enabled.write(False)

	@override
	def dispose(self):
		"""Clean up the result and its observe effect."""
		if self._interval_effect is not None and not self._interval_effect.__disposed__:
			self._interval_effect.dispose()
		if not self._observe_effect.__disposed__:
			self._observe_effect.dispose()


class QueryProperty(Generic[T, TState], InitializableProperty):
	"""
	Descriptor for state-bound queries.

	Usage:
	    class S(ps.State):
	        @ps.query()
	        async def user(self) -> User: ...

	        @user.key
	        def _user_key(self):
	            return ("user", self.user_id)
	"""

	name: str
	_fetch_fn: "Callable[[TState], Awaitable[T]]"
	_keep_alive: bool
	_keep_previous_data: bool
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_retries: int
	_retry_delay: float
	_initial_data_updated_at: float | dt.datetime | None
	_enabled: bool
	_initial_data: T | Callable[[TState], T] | None
	_key: QueryKey | Callable[[TState], QueryKey] | None
	# Not using OnSuccessFn and OnErrorFn since unions of callables are not well
	# supported in the type system. We just need to be careful to use
	# call_flexible to invoke these functions.
	_on_success_fn: Callable[[TState, T], Any] | None
	_on_error_fn: Callable[[TState, Exception], Any] | None
	_fetch_on_mount: bool
	_priv_result: str

	def __init__(
		self,
		name: str,
		fetch_fn: "Callable[[TState], Awaitable[T]]",
		keep_previous_data: bool = False,
		stale_time: float = 0.0,
		gc_time: float = 300.0,
		refetch_interval: float | None = None,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data_updated_at: float | dt.datetime | None = None,
		enabled: bool = True,
		fetch_on_mount: bool = True,
		key: QueryKey | Callable[[TState], QueryKey] | None = None,
	):
		self.name = name
		self._fetch_fn = fetch_fn
		self._key = key
		self._on_success_fn = None
		self._on_error_fn = None
		self._keep_previous_data = keep_previous_data
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._refetch_interval = refetch_interval
		self._retries = retries
		self._retry_delay = retry_delay
		self._initial_data_updated_at = initial_data_updated_at
		self._initial_data = MISSING  # pyright: ignore[reportAttributeAccessIssue]
		self._enabled = enabled
		self._fetch_on_mount = fetch_on_mount
		self._priv_result = f"__query_{name}"

	# Decorator to attach a key function
	def key(self, fn: Callable[[TState], QueryKey]):
		if self._key is not None:
			raise RuntimeError(
				f"Cannot use @{self.name}.key decorator when a key is already provided to @query(key=...)."
			)
		self._key = fn
		return fn

	# Decorator to attach a function providing initial data
	def initial_data(self, fn: Callable[[TState], T]):
		if self._initial_data is not MISSING:
			raise RuntimeError(
				f"Duplicate initial_data() decorator for query '{self.name}'. Only one is allowed."
			)
		self._initial_data = fn
		return fn

	# Decorator to attach an on-success handler (sync or async)
	def on_success(self, fn: OnSuccessFn[TState, T]):
		if self._on_success_fn is not None:
			raise RuntimeError(
				f"Duplicate on_success() decorator for query '{self.name}'. Only one is allowed."
			)
		self._on_success_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	# Decorator to attach an on-error handler (sync or async)
	def on_error(self, fn: OnErrorFn[TState]):
		if self._on_error_fn is not None:
			raise RuntimeError(
				f"Duplicate on_error() decorator for query '{self.name}'. Only one is allowed."
			)
		self._on_error_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	@override
	def initialize(
		self, state: Any, name: str
	) -> KeyedQueryResult[T] | UnkeyedQueryResult[T]:
		# Return cached query instance if present
		result: KeyedQueryResult[T] | UnkeyedQueryResult[T] | None = getattr(
			state, self._priv_result, None
		)
		if result:
			# Don't re-initialize, just return the cached instance
			return result

		# Bind methods to this instance
		fetch_fn = bind_state(state, self._fetch_fn)
		initial_data = cast(
			T | None,
			(
				call_flexible(self._initial_data, state)
				if callable(self._initial_data)
				else self._initial_data
			),
		)

		if self._key is None:
			# Unkeyed query: create UnkeyedQuery with single observer
			result = self._create_unkeyed(
				fetch_fn,
				initial_data,
				self._initial_data_updated_at,
				state,
			)
		else:
			# Keyed query: use session-wide QueryStore
			result = self._create_keyed(
				state,
				fetch_fn,
				initial_data,
				self._initial_data_updated_at,
			)

		# Store result on the instance
		setattr(state, self._priv_result, result)
		return result

	def _create_keyed(
		self,
		state: TState,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None,
		initial_data_updated_at: float | dt.datetime | None,
	) -> KeyedQueryResult[T]:
		"""Create or get a keyed query from the session store."""
		assert self._key is not None

		# Create a Computed for the key - passthrough for constant keys, reactive for function keys
		if callable(self._key):
			key_computed = Computed(
				bind_state(state, self._key), name=f"query.key.{self.name}"
			)
		else:
			const_key = self._key  # ensure a constant reference
			key_computed = Computed(lambda: const_key, name=f"query.key.{self.name}")

		render = PulseContext.get().render
		if render is None:
			raise RuntimeError("No render session available")
		store = render.query_store

		def query() -> KeyedQuery[T]:
			key = key_computed()
			# Use Untrack to avoid an error due to creating an Effect within a computed
			with Untrack():
				return store.ensure(
					key,
					initial_data,
					initial_data_updated_at=initial_data_updated_at,
					gc_time=self._gc_time,
					retries=self._retries,
					retry_delay=self._retry_delay,
				)

		query_computed = Computed(query, name=f"query.{self.name}")

		return KeyedQueryResult[T](
			query=query_computed,
			fetch_fn=fetch_fn,
			stale_time=self._stale_time,
			keep_previous_data=self._keep_previous_data,
			gc_time=self._gc_time,
			refetch_interval=self._refetch_interval,
			on_success=bind_state(state, self._on_success_fn)
			if self._on_success_fn
			else None,
			on_error=bind_state(state, self._on_error_fn)
			if self._on_error_fn
			else None,
			enabled=self._enabled,
			fetch_on_mount=self._fetch_on_mount,
		)

	def _create_unkeyed(
		self,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None,
		initial_data_updated_at: float | dt.datetime | None,
		state: TState,
	) -> UnkeyedQueryResult[T]:
		"""Create a private unkeyed query."""
		return UnkeyedQueryResult[T](
			fetch_fn=fetch_fn,
			on_success=bind_state(state, self._on_success_fn)
			if self._on_success_fn
			else None,
			on_error=bind_state(state, self._on_error_fn)
			if self._on_error_fn
			else None,
			retries=self._retries,
			retry_delay=self._retry_delay,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=self._gc_time,
			stale_time=self._stale_time,
			keep_previous_data=self._keep_previous_data,
			refetch_interval=self._refetch_interval,
			enabled=self._enabled,
			fetch_on_mount=self._fetch_on_mount,
		)

	def __get__(self, obj: Any, objtype: Any = None) -> "QueryResult[T]":
		if obj is None:
			return self  # pyright: ignore[reportReturnType]
		return self.initialize(obj, self.name)


@overload
def query(
	fn: Callable[[TState], Awaitable[T]],
	*,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	refetch_interval: float | None = None,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | dt.datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
	key: QueryKey | None = None,
) -> QueryProperty[T, TState]: ...


@overload
def query(
	fn: None = None,
	*,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	refetch_interval: float | None = None,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | dt.datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
	key: QueryKey | None = None,
) -> Callable[[Callable[[TState], Awaitable[T]]], QueryProperty[T, TState]]: ...


def query(
	fn: Callable[[TState], Awaitable[T]] | None = None,
	*,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	refetch_interval: float | None = None,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | dt.datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
	key: QueryKey | None = None,
):
	def decorator(
		func: Callable[[TState], Awaitable[T]], /
	) -> QueryProperty[T, TState]:
		sig = inspect.signature(func)
		params = list(sig.parameters.values())
		# Only state-method form supported for now (single 'self')
		if not (len(params) == 1 and params[0].name == "self"):
			raise TypeError("@query currently only supports state methods (self)")

		return QueryProperty(
			func.__name__,
			func,
			stale_time=stale_time,
			gc_time=gc_time if gc_time is not None else 300.0,
			refetch_interval=refetch_interval,
			keep_previous_data=keep_previous_data,
			retries=retries,
			retry_delay=RETRY_DELAY_DEFAULT if retry_delay is None else retry_delay,
			initial_data_updated_at=initial_data_updated_at,
			enabled=enabled,
			fetch_on_mount=fetch_on_mount,
			key=key,
		)

	if fn:
		return decorator(fn)
	return decorator
