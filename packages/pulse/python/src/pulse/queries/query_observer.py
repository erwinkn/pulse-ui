import inspect
import time
from collections.abc import Awaitable, Callable
from typing import (
	Any,
	Generic,
	TypeVar,
	cast,
	override,
)

from pulse.context import PulseContext
from pulse.helpers import MISSING, Disposable
from pulse.queries.common import OnErrorFn, OnSuccessFn, bind_state
from pulse.queries.query import (
	RETRY_DELAY_DEFAULT,
	Query,
	QueryFetchStatus,
	QueryKey,
	QueryStatus,
)
from pulse.reactive import Computed, Effect, Untrack
from pulse.state import InitializableProperty, State

T = TypeVar("T")
TState = TypeVar("TState", bound=State)


class QueryResult(Generic[T], Disposable):
	"""
	Thin wrapper around Query that adds callbacks, staleness tracking,
	and observation lifecycle.

	For keyed queries, uses a Computed to resolve the correct query based on the key.
	"""

	_query: Computed[Query[T]]
	_stale_time: float
	_gc_time: float
	_keep_previous_data: bool
	_on_success: Callable[[T], Awaitable[None] | None] | None
	_on_error: Callable[[Exception], Awaitable[None] | None] | None
	_callback_effect: Effect
	_observe_effect: Effect
	_data_computed: Computed[T | None]
	_disposed_data: T | None

	def __init__(
		self,
		query: Computed[Query[T]],
		stale_time: float = 0.0,
		gc_time: float = 300.0,
		keep_previous_data: bool = False,
		on_success: Callable[[T], Awaitable[None] | None] | None = None,
		on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
	):
		self._query = query
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._keep_previous_data = keep_previous_data
		self._on_success = on_success
		self._on_error = on_error
		self._disposed_data = None

		def observe_effect():
			query = self._query()
			with Untrack():
				# This may create an effect, which should live independently of our observe effect
				query.observe(self)

			# If stale or loading, schedule refetch
			if self.is_stale():
				query.invalidate()

			# Return cleanup function that captures the observer
			return lambda: query.unobserve(self)

		self._observe_effect = Effect(
			observe_effect,
			name=f"query_observe({self._query().key})",
			immediate=True,
		)
		self._data_computed = Computed(
			self._data_computed_fn, name=f"query_data({self._query().key})"
		)

	@property
	def status(self) -> QueryStatus:
		return self._query().status()

	@property
	def fetch_status(self) -> QueryFetchStatus:
		return self._query().fetch_status()

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
		return self.fetch_status == "fetching"

	@property
	def error(self) -> Exception | None:
		return self._query().error.read()

	def _data_computed_fn(self, prev: T | None) -> T | None:
		query = self._query()
		if self._keep_previous_data and query.status() != "success":
			return prev
		return query.data()

	@property
	def data(self) -> T | None:
		return self._data_computed()

	@property
	def has_loaded(self) -> bool:
		return self.status in ("success", "error")

	def is_stale(self) -> bool:
		"""Check if the query data is stale based on stale_time."""
		query = self._query()
		return (time.time() - query.last_updated.read()) > self._stale_time

	async def refetch(self, cancel_refetch: bool = True) -> T:
		"""Refetch the query data."""
		return await self._query().refetch(cancel_refetch=cancel_refetch)

	async def wait(self) -> T:
		return await self._query().wait()

	def invalidate(self):
		"""Mark the query as stale and refetch if there are observers."""
		query = self._query()
		query.invalidate()

	def set_data(self, data: T):
		"""Optimistically set data without changing loading/error state."""
		query = self._query()
		query.data.write(data)

	@override
	def dispose(self):
		"""Clean up the result and its observe effect."""
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
	_retries: int
	_retry_delay: float
	_initial_data: T | Callable[[TState], T] | None
	_key_fn: Callable[[TState], QueryKey] | None
	# Not using OnSuccessFn and OnErrorFn since unions of callables are not well
	# supported in the type system. We just need to be careful to use
	# call_flexible to invoke these functions.
	_on_success_fn: Callable[[TState, T], Any] | None
	_on_error_fn: Callable[[TState, Exception], Any] | None
	_priv_result: str

	def __init__(
		self,
		name: str,
		fetch_fn: "Callable[[TState], Awaitable[T]]",
		keep_previous_data: bool = False,
		stale_time: float = 0.0,
		gc_time: float = 300.0,
		retries: int = 3,
		retry_delay: float = RETRY_DELAY_DEFAULT,
		initial: T | Callable[[TState], T] | None = MISSING,
		key: Callable[[TState], QueryKey] | None = None,
		on_success: OnSuccessFn[TState, T] | None = None,
		on_error: OnErrorFn[TState] | None = None,
	):
		self.name = name
		self._fetch_fn = fetch_fn
		self._key_fn = None
		self._on_success_fn = on_success  # pyright: ignore[reportAttributeAccessIssue]
		self._on_error_fn = on_error  # pyright: ignore[reportAttributeAccessIssue]
		self._keep_previous_data = keep_previous_data
		self._stale_time = stale_time
		self._gc_time = gc_time
		self._retries = retries
		self._retry_delay = retry_delay
		self._initial_data = initial
		self._priv_result = f"__query_{name}"

	# Decorator to attach a key function
	def key(self, fn: Callable[[TState], QueryKey]):
		if self._key_fn is not None:
			raise RuntimeError(
				f"Duplicate key() decorator for query '{self.name}'. Only one is allowed."
			)
		self._key_fn = fn
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
				self._initial_data(state)
				if callable(self._initial_data)
				and len(inspect.signature(self._initial_data).parameters) == 1
				else self._initial_data
			),
		)

		if self._key_fn:
			# Keyed query: use session-wide QueryStore
			query = self._resolve_keyed(state, fetch_fn, initial_data)
		else:
			# Unkeyed query: create private Query
			query = self._resolve_unkeyed(fetch_fn, initial_data)

		# Wrap query in QueryResult
		result = QueryResult[T](
			query=query,
			stale_time=self._stale_time,
			keep_previous_data=self._keep_previous_data,
			gc_time=self._gc_time,
			on_success=bind_state(state, self._on_success_fn)
			if self._on_success_fn
			else None,
			on_error=bind_state(state, self._on_error_fn)
			if self._on_error_fn
			else None,
		)

		# Store result on the instance
		setattr(state, self._priv_result, result)
		return result

	def _resolve_keyed(
		self,
		state: TState,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None,
	) -> Computed[Query[T]]:
		"""Create or get a keyed query from the session store using a Computed."""
		assert self._key_fn is not None

		key_computed = Computed(
			bind_state(state, self._key_fn), name=f"query.key.{self.name}"
		)
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
				gc_time=self._gc_time,
				retries=self._retries,
				retry_delay=self._retry_delay,
			)

		return Computed(query, name=f"query.{self.name}")

	def _resolve_unkeyed(
		self,
		fetch_fn: Callable[[], Awaitable[T]],
		initial_data: T | None,
	) -> Computed[Query[T]]:
		"""Create a private unkeyed query."""
		query = Query[T](
			key=None,
			fn=fetch_fn,
			initial_data=initial_data,
			gc_time=self._gc_time,
			retries=self._retries,
			retry_delay=self._retry_delay,
		)
		return Computed(lambda: query, name=f"query.{self.name}")

	def __get__(self, obj: Any, objtype: Any = None) -> QueryResult[T]:
		if obj is None:
			return self  # pyright: ignore[reportReturnType]
		return self.initialize(obj, self.name)


class QueryResultWithInitial(QueryResult[T]):
	@property
	@override
	def data(self) -> T:
		return cast(T, super().data)

	@property
	@override
	def has_loaded(self) -> bool:  # mirror base for completeness
		return super().has_loaded


class QueryPropertyWithInitial(QueryProperty[T, TState]):
	@override
	def __get__(self, obj: Any, objtype: Any = None) -> QueryResultWithInitial[T]:
		# Reuse base initialization but narrow the return type for type-checkers
		return cast(QueryResultWithInitial[T], super().__get__(obj, objtype))
