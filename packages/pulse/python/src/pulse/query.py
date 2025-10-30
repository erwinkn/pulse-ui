import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import (
	Any,
	Generic,
	TypeVar,
	TypeVarTuple,
	cast,
	override,
)

from pulse.helpers import call_flexible, maybe_await
from pulse.reactive import AsyncEffect, Computed, EffectCleanup, Signal
from pulse.state import InitializableProperty, State

T = TypeVar("T")
TState = TypeVar("TState", bound="State")
Args = TypeVarTuple("Args")
R = TypeVar("R")

# Type alias matching AsyncEffectFn from reactive.py
AsyncEffectFn = Callable[[], Coroutine[Any, Any, EffectCleanup | None]]


class QueryAsyncEffect(AsyncEffect):
	"""
	Specialized AsyncEffect for queries that synchronously clears query data
	when rescheduled (if keep_previous_data is False).
	"""

	_result: "QueryResult[Any]"
	_keep_previous_data: bool

	def __init__(
		self,
		fn: AsyncEffectFn,
		result: "QueryResult[Any]",
		keep_previous_data: bool,
		name: str | None = None,
		deps: list[Signal[Any] | Computed[Any]] | None = None,
	):
		super().__init__(fn, name=name, deps=deps)
		self._result = result
		self._keep_previous_data = keep_previous_data

	@override
	def push_change(self, *, keep_previous_data: bool | None = None):
		# Synchronously clear data before scheduling the effect to run.
		# This ensures renders see the loading state immediately, not stale data.
		effective_keep_previous_data = (
			keep_previous_data if keep_previous_data is not None else self._keep_previous_data
		)
		self._result._set_loading(clear_data=not effective_keep_previous_data)  # pyright: ignore[reportPrivateUsage]
		super().push_change()


class QueryResult(Generic[T]):
	def __init__(self, initial_data: T | None = None):
		# print("[QueryResult] initialize")
		self._is_loading: Signal[bool] = Signal(True, name="query.is_loading")
		self._is_error: Signal[bool] = Signal(False, name="query.is_error")
		self._error: Signal[Exception | None] = Signal(None, name="query.error")
		# Store initial data so we can preserve non-None semantics when requested
		self._initial_data: T | None = initial_data
		self._data: Signal[T | None] = Signal(initial_data, name="query.data")
		# Tracks whether at least one load cycle completed (success or error)
		self._has_loaded: Signal[bool] = Signal(False, name="query.has_loaded")
		# Effect driving this query (attached by QueryProperty)
		self._effect: QueryAsyncEffect | None = None

	@property
	def is_loading(self) -> bool:
		# print(f"[QueryResult] Accessing is_loading = {self._is_loading.read()}")
		return self._is_loading.read()

	@property
	def is_error(self) -> bool:
		# print(f"[QueryResult] Accessing is_error = {self._is_error.read()}")
		return self._is_error.read()

	@property
	def error(self) -> Exception | None:
		# print(f"[QueryResult] Accessing error = {self._error.read()}")
		return self._error.read()

	@property
	def data(self) -> T | None:
		# print(f"[QueryResult] Accessing data = {self._data.read()}")
		return self._data.read()

	@property
	def has_loaded(self) -> bool:
		return self._has_loaded.read()

	def attach_effect(self, effect: QueryAsyncEffect) -> None:
		self._effect = effect

	def refetch(self, *, keep_previous_data: bool | None = None) -> None:
		if self._effect is None:
			return
		self._effect.push_change(keep_previous_data=keep_previous_data)

	def dispose(self) -> None:
		if self._effect is None:
			return
		self._effect.dispose()

	# Internal setters used by the query machinery
	def _set_loading(self, *, clear_data: bool = False):
		# print("[QueryResult] set loading=True")
		self._is_loading.write(True)
		self._is_error.write(False)
		self._error.write(None)
		if clear_data:
			# If there was an explicit initial value, reset to it; otherwise clear
			self._data.write(self._initial_data)

	def _set_success(self, data: T):
		# print(f"[QueryResult] set success data={data!r}")
		self._data.write(data)
		self._is_loading.write(False)
		self._is_error.write(False)
		self._error.write(None)
		self._has_loaded.write(True)

	def _set_error(self, err: Exception):
		# print(f"[QueryResult] set error err={err!r}")
		self._error.write(err)
		self._is_loading.write(False)
		self._is_error.write(True)
		self._has_loaded.write(True)

	# Public mutator useful for optimistic updates; does not change loading/error flags
	def set_data(self, data: T):
		self._data.write(data)

	# Public mutator to set initial data before the first load completes.
	# If called after the first load, it is ignored.
	def set_initial_data(self, data: T):
		if self._has_loaded.read():
			return
		self._initial_data = data
		self._data.write(data)

	# Public helpers mirroring internal transitions
	def set_loading(self, *, clear_data: bool = False) -> None:
		self._set_loading(clear_data=clear_data)

	def set_success(self, data: T) -> None:
		self._set_success(data)

	def set_error(self, err: Exception) -> None:
		self._set_error(err)


OnSuccessFn = Callable[[TState], Any] | Callable[[TState, T], Any]
OnErrorFn = Callable[[TState], Any] | Callable[[TState, Exception], Any]


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
	_initial: T | None
	_key_fn: Callable[[TState], tuple[Any, ...]] | None
	_initial_data_fn: Callable[[TState], T] | None
	# Not using OnSuccessFn and OnErrorFn since unions of callables are not well
	# supported in the type system. We just need to be careful to use
	# call_flexible to invoke these functions.
	_on_success_fn: Callable[[TState, Exception], Any] | None
	_on_error_fn: Callable[[TState, T], Any] | None

	_priv_query: str
	_priv_effect: str
	_priv_key_comp: str
	_priv_initial_fn: str
	_priv_initial_applied: str

	def __init__(
		self,
		name: str,
		fetch_fn: "Callable[[TState], Awaitable[T]]",
		keep_alive: bool = False,
		keep_previous_data: bool = False,
		initial: T | None = None,
	):
		self.name = name
		self._fetch_fn = fetch_fn
		self._key_fn = None
		self._initial_data_fn = None
		# Single handlers; error if set more than once
		self._on_success_fn = None
		self._on_error_fn = None
		self._keep_alive = keep_alive
		self._keep_previous_data = keep_previous_data
		self._initial = initial
		self._priv_query = f"__query_{name}"
		self._priv_effect = f"__query_effect_{name}"
		self._priv_key_comp = f"__query_key_{name}"
		self._priv_initial_fn = f"__query_initial_fn_{name}"
		self._priv_initial_applied = f"__query_initial_applied_{name}"

	# Decorator to attach a key function
	def key(self, fn: Callable[[TState], tuple[Any, ...]]):
		if self._key_fn is not None:
			raise RuntimeError(
				f"Duplicate key() decorator for query '{self.name}'. Only one is allowed."
			)
		self._key_fn = fn
		return fn

	# Decorator to attach a function providing initial data
	def initial_data(self, fn: Callable[[TState], T]):
		if self._initial_data_fn is not None:
			raise RuntimeError(
				f"Duplicate initial_data() decorator for query '{self.name}'. Only one is allowed."
			)
		self._initial_data_fn = fn
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
		query: QueryResult[T] | None = getattr(state, self._priv_query, None)
		if query:
			# print(f"[QueryProperty:{self.name}] return cached StateQuery")
			return query

		# key_fn being None means auto-tracked mode

		# Bind methods to this instance
		bound_fetch = bind_state(state, self._fetch_fn)
		bound_on_success = (
			bind_state(state, self._on_success_fn) if self._on_success_fn else None
		)
		bound_on_error = (
			bind_state(state, self._on_error_fn) if self._on_error_fn else None
		)
		bound_initial_data = (
			bind_state(state, self._initial_data_fn) if self._initial_data_fn else None
		)
		# print(f"[QueryProperty:{self.name}] bound fetch and key/handlers")

		# Defer evaluating initial_data provider until after user __init__ by
		# storing it on the instance and marking it unapplied. Use constructor
		# `initial` as the initial visible value for now.
		setattr(state, self._priv_initial_fn, bound_initial_data)
		setattr(state, self._priv_initial_applied, False)
		initial_value: T | None = self._initial

		result = QueryResult[T](initial_data=initial_value)

		key_computed: Computed[tuple[Any, ...]] | None = None
		if self._key_fn:
			bound_key_fn = bind_state(state, self._key_fn)
			key_computed = Computed(bound_key_fn, name=f"query.key.{self.name}")
			setattr(state, self._priv_key_comp, key_computed)

		inflight_key: tuple[Any, ...] | None = None

		async def run_effect():
			# print(f"[QueryProperty:{self.name}] effect RUN")
			# In key mode, deduplicate same-key concurrent reruns
			if key_computed:
				key = key_computed()

				nonlocal inflight_key
				# De-duplicate same-key concurrent reruns
				if inflight_key == key:
					return None
				inflight_key = key

			# Set loading immediately; optionally clear previous data
			result.set_loading(clear_data=not self._keep_previous_data)

			try:
				data = await bound_fetch()
			except asyncio.CancelledError:
				# Cancellation is expected during reruns; swallow
				return None
			except Exception as e:
				result.set_error(e)
				# Invoke error handler if provided
				if bound_on_error:
					await maybe_await(call_flexible(bound_on_error, e))
			else:
				result.set_success(data)
				# Invoke success handler if provided
				if bound_on_success:
					await maybe_await(call_flexible(bound_on_success, data))
			finally:
				inflight_key = None

		# In key mode, depend only on key via explicit deps
		if key_computed is not None:
			effect = QueryAsyncEffect(
				run_effect,
				result=result,
				keep_previous_data=self._keep_previous_data,
				name=f"query.effect.{self.name}",
				deps=[key_computed],
			)
		else:
			effect = QueryAsyncEffect(
				run_effect,
				result=result,
				keep_previous_data=self._keep_previous_data,
				name=f"query.effect.{self.name}",
			)
		# print(f"[QueryProperty:{self.name}] created Effect name={effect.name}")

		# Expose the effect on the instance so State.effects() sees it
		setattr(state, self._priv_effect, effect)
		# Attach effect to result and expose result directly
		result.attach_effect(effect)
		setattr(state, self._priv_query, result)

		# if not self.keep_alive:

		# 	def on_obs(count: int):
		# 		if count == 0:
		# 			# print("[QueryProperty] Disposing of effect due to no observers")
		# 			effect.dispose()

		# Stop when no one observes key or data
		# result._data.on_observer_change(on_obs)
		# result._is_error.on_observer_change(on_obs)
		# result._is_loading.on_observer_change(on_obs)

		return result

	def __get__(self, obj: Any, objtype: Any = None) -> QueryResult[T]:
		if obj is None:
			return self  # pyright: ignore[reportReturnType]
		query = self.initialize(obj, self.name)
		# Apply initial_data provider once, after state __init__, before first load
		try:
			applied = bool(getattr(obj, self._priv_initial_applied, False))
		except Exception:
			applied = True  # fail safe: do not attempt if attribute missing
		if not applied and not query.has_loaded:
			bound_initial = getattr(obj, self._priv_initial_fn, None)
			if callable(bound_initial):
				try:
					value = bound_initial()
					if value is not None:
						query.set_initial_data(value)  # pyright: ignore[reportArgumentType]
				except Exception:
					pass
			try:
				setattr(obj, self._priv_initial_applied, True)
			except Exception:
				pass
		return query


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


def bind_state(state: TState, fn: Callable[[TState, *Args], R]) -> Callable[[*Args], R]:
	"Type-safe helper to bind a method to a state"
	return fn.__get__(state, state.__class__)
