import asyncio
import datetime as dt
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
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
from pulse.reactive import AsyncEffect, Computed, Effect, Signal, Untrack
from pulse.state import InitializableProperty, State

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


class Query(Generic[T], Disposable):
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
	is_fetching: Signal[bool]
	retries: Signal[int]
	retry_reason: Signal[Exception | None]

	_observers: "list[QueryResult[T]]"
	_effect: AsyncEffect | None
	_gc_handle: asyncio.TimerHandle | None

	def __init__(
		self,
		key: QueryKey | None,
		fn: Callable[[], Awaitable[T]],
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial_data: T | None = MISSING,
		initial_data_updated_at: float | dt.datetime | None = None,
		gc_time: float = 300.0,
		on_dispose: Callable[[Any], None] | None = None,
	):
		self.key = key
		self.fn = fn
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
			None if initial_data is MISSING else initial_data, name=f"query.data({key})"
		)
		self.error = Signal(None, name=f"query.error({key})")

		self.last_updated = Signal(
			0.0,
			name=f"query.last_updated({key})",
		)
		if initial_data_updated_at:
			self.set_updated_at(initial_data_updated_at)

		self.status = Signal(
			"loading" if initial_data is MISSING else "success",
			name=f"query.status({key})",
		)
		self.is_fetching = Signal(False, name=f"query.is_fetching({key})")
		self.retries = Signal(0, name=f"query.retries({key})")
		self.retry_reason = Signal(None, name=f"query.retry_reason({key})")

		self._observers = []
		self._gc_handle = None
		# Effect is created lazily on first observation
		self._effect = None

	def set_data(
		self,
		data: T | Callable[[T | None], T],
		*,
		updated_at: float | dt.datetime | None = None,
	):
		"""Set data manually, accepting a value or updater function."""
		current = self.data.read()
		new_value = cast(T, data(current) if callable(data) else data)
		self._set_success(new_value, manual=True)
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
		self._set_error(error, manual=True)
		if updated_at is not None:
			self.set_updated_at(updated_at)

	def _set_success(self, data: T, manual: bool = False):
		self.data.write(data)
		self.last_updated.write(time.time())
		self.error.write(None)
		self.status.write("success")
		if not manual:
			self.is_fetching.write(False)
			self.retries.write(0)
			self.retry_reason.write(None)

	def _set_error(self, error: Exception, manual: bool = False):
		self.error.write(error)
		self.last_updated.write(time.time())
		self.status.write("error")
		if not manual:
			self.is_fetching.write(False)
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
				fetcher=self,
				name=f"query_effect({self.key})",
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
				for obs in self._observers:
					if obs._on_success:  # pyright: ignore[reportPrivateUsage]
						await maybe_await(call_flexible(obs._on_success, result))  # pyright: ignore[reportPrivateUsage]
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
					for obs in self._observers:
						if obs._on_error:  # pyright: ignore[reportPrivateUsage]
							await maybe_await(call_flexible(obs._on_error, e))  # pyright: ignore[reportPrivateUsage]
					return

	async def refetch(self, cancel_refetch: bool = True) -> ActionResult[T]:
		"""
		Reruns the query and returns the result.
		If cancel_refetch is True (default), cancels any in-flight request and starts a new one.
		If cancel_refetch is False, deduplicates requests if one is already in flight.
		"""
		if cancel_refetch or not self.is_fetching():
			self.effect.schedule()
		return await self.wait()

	async def wait(self) -> ActionResult[T]:
		# If loading and no task, schedule a refetch
		if self.status() == "loading" and not self.is_fetching():
			self.effect.schedule()
		await self.effect.wait()
		# Return result based on current state
		if self.status() == "error":
			return ActionError(cast(Exception, self.error.read()))
		return ActionSuccess(cast(T, self.data.read()))

	def invalidate(self, cancel_refetch: bool = False):
		"""
		Marks query as stale. If there are active observers, triggers a refetch.
		"""
		should_schedule = not self.effect.is_scheduled or cancel_refetch
		if should_schedule and len(self._observers) > 0:
			self.effect.schedule()

	def observe(
		self,
		observer: "QueryResult[T]",
	):
		_ = self.effect  # ensure effect is created
		self._observers.append(observer)
		self.cancel_gc()
		if observer._gc_time > 0:  # pyright: ignore[reportPrivateUsage]
			self.cfg.gc_time = max(self.cfg.gc_time, observer._gc_time)  # pyright: ignore[reportPrivateUsage]

	def unobserve(self, observer: "QueryResult[T]"):
		"""Unregister an observer. Schedules GC if no observers remain."""
		if observer in self._observers:
			self._observers.remove(observer)
		if len(self._observers) == 0:
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
		"""
		Cleans up the query entry, removing it from the store.
		"""
		if self._effect:
			self._effect.dispose()

		if self.cfg.on_dispose:
			self.cfg.on_dispose(self)


class QueryResult(Generic[T], Disposable):
	"""
	Thin wrapper around Query that adds callbacks, staleness tracking,
	and observation lifecycle.

	For keyed queries, uses a Computed to resolve the correct query based on the key.
	"""

	_query: Computed[Query[T]]
	_stale_time: float
	_gc_time: float
	_refetch_interval: float | None
	_keep_previous_data: bool
	_on_success: Callable[[T], Awaitable[None] | None] | None
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_callback_effect: Effect
	_observe_effect: Effect
	_interval_effect: Effect | None
	_data_computed: Computed[T | None]
	_disposed_data: T | None
	_enabled: Signal[bool]
	_fetch_on_mount: bool
	_is_observing: bool

	def __init__(
		self,
		query: Computed[Query[T]],
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
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._refetch_interval = refetch_interval
		self._keep_previous_data = keep_previous_data
		self._on_success = on_success
		self._on_error = on_error
		self._disposed_data = None
		self._enabled = Signal(enabled, name=f"query.enabled({query().key})")
		self._interval_effect = None

		def observe_effect():
			query = self._query()
			enabled = self._enabled()
			with Untrack():
				query.observe(self)

			# If stale or loading, schedule refetch (only when enabled)
			if enabled and fetch_on_mount and self.is_stale():
				query.invalidate()

			# Return cleanup function that captures the observer
			def cleanup():
				query.unobserve(self)

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
				self._query().invalidate()

		self._interval_effect = Effect(
			interval_fn,
			name=f"query_interval({self._query().key})",
			interval=interval,
			immediate=True,
		)

	@property
	def status(self) -> QueryStatus:
		return self._query().status()

	# Forward property reads to the query's signals (with automatic reactive tracking)
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
		"""Refetch the query data."""
		return await self._query().refetch(cancel_refetch=cancel_refetch)

	async def wait(self) -> ActionResult[T]:
		return await self._query().wait()

	def invalidate(self):
		"""Mark the query as stale and refetch if there are observers."""
		query = self._query()
		query.invalidate()

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
		if self._interval_effect is not None:
			self._interval_effect.dispose()
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
	def initialize(self, state: Any, name: str) -> QueryResult[T]:
		# Return cached query instance if present
		result: QueryResult[T] | None = getattr(state, self._priv_result, None)
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
			# Unkeyed query: create private Query
			query = self._resolve_unkeyed(
				fetch_fn,
				initial_data,
				self._initial_data_updated_at,
			)
		else:
			# Keyed query: use session-wide QueryStore
			query = self._resolve_keyed(
				state,
				fetch_fn,
				initial_data,
				self._initial_data_updated_at,
			)

		# Wrap query in QueryResult
		result = QueryResult[T](
			query=query,
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

		# Store result on the instance
		setattr(state, self._priv_result, result)
		return result

	def _resolve_keyed(
		self,
		state: TState,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None,
		initial_data_updated_at: float | dt.datetime | None,
	) -> Computed[Query[T]]:
		"""Create or get a keyed query from the session store using a Computed."""
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

		def query() -> Query[T]:
			key = key_computed()
			return store.ensure(
				key,
				fetch_fn,
				initial_data,
				initial_data_updated_at=initial_data_updated_at,
				gc_time=self._gc_time,
				retries=self._retries,
				retry_delay=self._retry_delay,
			)

		return Computed(query, name=f"query.{self.name}")

	def _resolve_unkeyed(
		self,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None,
		initial_data_updated_at: float | dt.datetime | None,
	) -> Computed[Query[T]]:
		"""Create a private unkeyed query."""
		query = Query[T](
			key=None,
			fn=fetch_fn,
			initial_data=initial_data,
			initial_data_updated_at=initial_data_updated_at,
			gc_time=self._gc_time,
			retries=self._retries,
			retry_delay=self._retry_delay,
		)
		return Computed(lambda: query, name=f"query.{self.name}")

	def __get__(self, obj: Any, objtype: Any = None) -> QueryResult[T]:
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
