# Separate file from reactive.py due to needing to import from state too

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, overload

from pulse.queries.common import OnErrorFn, OnSuccessFn
from pulse.queries.infinite_query import InfiniteQueryProperty
from pulse.queries.mutation import MutationProperty
from pulse.queries.query import RETRY_DELAY_DEFAULT, QueryProperty
from pulse.reactive import (
	AsyncEffect,
	AsyncEffectFn,
	Computed,
	Effect,
	EffectCleanup,
	EffectFn,
	Signal,
)
from pulse.state import ComputedProperty, State, StateEffect

T = TypeVar("T")
TState = TypeVar("TState", bound=State)
P = ParamSpec("P")


# -> @ps.computed The chalenge is:
# - We want to turn regular functions with no arguments into a Computed object
# - We want to turn state methods into a ComputedProperty (which wraps a
#   Computed, but gives it access to the State object).
@overload
def computed(fn: Callable[[], T], *, name: str | None = None) -> Computed[T]: ...
@overload
def computed(
	fn: Callable[[TState], T], *, name: str | None = None
) -> ComputedProperty[T]: ...
@overload
def computed(
	fn: None = None, *, name: str | None = None
) -> Callable[[Callable[[], T]], Computed[T]]: ...


def computed(fn: Callable[..., Any] | None = None, *, name: str | None = None):
	# The type checker is not happy if I don't specify the `/` here.
	def decorator(fn: Callable[..., Any], /):
		sig = inspect.signature(fn)
		params = list(sig.parameters.values())
		# Check if it's a method with exactly one argument called 'self'
		if len(params) == 1 and params[0].name == "self":
			return ComputedProperty(fn.__name__, fn)
		# If it has any arguments at all, it's not allowed (except for 'self')
		if len(params) > 0:
			raise TypeError(
				f"@computed: Function '{fn.__name__}' must take no arguments or a single 'self' argument"
			)
		return Computed(fn, name=name or fn.__name__)

	if fn is not None:
		return decorator(fn)
	else:
		return decorator


StateEffectFn = Callable[[TState], EffectCleanup | None]
AsyncStateEffectFn = Callable[[TState], Awaitable[EffectCleanup | None]]


class EffectBuilder(Protocol):
	@overload
	def __call__(self, fn: EffectFn | StateEffectFn[Any]) -> Effect: ...
	@overload
	def __call__(self, fn: AsyncEffectFn | AsyncStateEffectFn[Any]) -> AsyncEffect: ...
	def __call__(
		self,
		fn: EffectFn | StateEffectFn[Any] | AsyncEffectFn | AsyncStateEffectFn[Any],
	) -> Effect | AsyncEffect: ...


@overload
def effect(
	fn: EffectFn,
	*,
	name: str | None = None,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
) -> Effect: ...


@overload
def effect(
	fn: AsyncEffectFn,
	*,
	name: str | None = None,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
) -> AsyncEffect: ...
# In practice this overload returns a StateEffect, but it gets converted into an
# Effect at state instantiation.
@overload
def effect(fn: StateEffectFn[Any]) -> Effect: ...
@overload
def effect(fn: AsyncStateEffectFn[Any]) -> AsyncEffect: ...
@overload
def effect(
	fn: None = None,
	*,
	name: str | None = None,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
) -> EffectBuilder: ...


def effect(
	fn: Callable[..., Any] | None = None,
	*,
	name: str | None = None,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
):
	# The type checker is not happy if I don't specify the `/` here.
	def decorator(func: Callable[..., Any], /):
		sig = inspect.signature(func)
		params = list(sig.parameters.values())

		# Disallow intermediate + async
		if immediate and inspect.iscoroutinefunction(func):
			raise ValueError("Async effects cannot have immediate=True")

		if len(params) == 1 and params[0].name == "self":
			return StateEffect(
				func,
				name=name,
				immediate=immediate,
				lazy=lazy,
				on_error=on_error,
				deps=deps,
			)

		if len(params) > 0:
			raise TypeError(
				f"@effect: Function '{func.__name__}' must take no arguments or a single 'self' argument"
			)

		# This is a standalone effect function. Choose subclass based on async-ness
		if inspect.iscoroutinefunction(func):
			return AsyncEffect(
				func,  # type: ignore[arg-type]
				name=name or func.__name__,
				lazy=lazy,
				on_error=on_error,
				deps=deps,
			)
		return Effect(
			func,  # type: ignore[arg-type]
			name=name or func.__name__,
			immediate=immediate,
			lazy=lazy,
			on_error=on_error,
			deps=deps,
		)

	if fn:
		return decorator(fn)
	return decorator


# -----------------
# Query decorator
# -----------------


@overload
def query(
	fn: Callable[[TState], Awaitable[T]],
	*,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
) -> QueryProperty[T, TState]: ...


@overload
def query(
	fn: None = None,
	*,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
) -> Callable[[Callable[[TState], Awaitable[T]]], QueryProperty[T, TState]]: ...


def query(
	fn: Callable[[TState], Awaitable[T]] | None = None,
	*,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
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
			keep_previous_data=keep_previous_data,
			retries=retries,
			retry_delay=RETRY_DELAY_DEFAULT if retry_delay is None else retry_delay,
			initial_data_updated_at=initial_data_updated_at,
			enabled=enabled,
			fetch_on_mount=fetch_on_mount,
		)

	if fn:
		return decorator(fn)
	return decorator


# -----------------
# Infinite query decorator
# -----------------


TIPage = TypeVar("TIPage")
TIPageParam = TypeVar("TIPageParam")


@overload
def infinite_query(
	fn: Callable[[TState, TIPageParam], Awaitable[TIPage]],
	*,
	initial_page_param: TIPageParam,
	max_pages: int = 0,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
) -> InfiniteQueryProperty[TIPage, TIPageParam, TState]: ...


@overload
def infinite_query(
	fn: None = None,
	*,
	initial_page_param: TIPageParam,
	max_pages: int = 0,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
) -> Callable[
	[Callable[[TState, Any], Awaitable[TIPage]]],
	InfiniteQueryProperty[TIPage, TIPageParam, TState],
]: ...


def infinite_query(
	fn: Callable[[TState, TIPageParam], Awaitable[TIPage]] | None = None,
	*,
	initial_page_param: TIPageParam,
	max_pages: int = 0,
	stale_time: float = 0.0,
	gc_time: float | None = 300.0,
	keep_previous_data: bool = False,
	retries: int = 3,
	retry_delay: float | None = None,
	initial_data_updated_at: float | datetime | None = None,
	enabled: bool = True,
	fetch_on_mount: bool = True,
):
	def decorator(
		func: Callable[[TState, TIPageParam], Awaitable[TIPage]], /
	) -> InfiniteQueryProperty[TIPage, TIPageParam, TState]:
		sig = inspect.signature(func)
		params = list(sig.parameters.values())
		if not (len(params) == 2 and params[0].name == "self"):
			raise TypeError(
				"@infinite_query must be applied to a state method with signature (self, page_param)"
			)

		return InfiniteQueryProperty(
			func.__name__,
			func,
			initial_page_param=initial_page_param,
			max_pages=max_pages,
			stale_time=stale_time,
			gc_time=gc_time if gc_time is not None else 300.0,
			keep_previous_data=keep_previous_data,
			retries=retries,
			retry_delay=RETRY_DELAY_DEFAULT if retry_delay is None else retry_delay,
			initial_data_updated_at=initial_data_updated_at,
			enabled=enabled,
			fetch_on_mount=fetch_on_mount,
		)

	if fn:
		return decorator(fn)
	return decorator


# -----------------
# Mutation decorator
# -----------------
@overload
def mutation(
	fn: Callable[Concatenate[TState, P], Awaitable[T]],
	*,
	on_success: OnSuccessFn[TState, T] | None = None,
	on_error: OnErrorFn[TState] | None = None,
) -> MutationProperty[T, TState, P]: ...


@overload
def mutation(
	fn: None = None,
	*,
	on_success: OnSuccessFn[TState, T] | None = None,
	on_error: OnErrorFn[TState] | None = None,
) -> Callable[
	[Callable[Concatenate[TState, P], Awaitable[T]]], MutationProperty[T, TState, P]
]: ...


def mutation(
	fn: Callable[Concatenate[TState, P], Awaitable[T]] | None = None,
	*,
	on_success: OnSuccessFn[TState, T] | None = None,
	on_error: OnErrorFn[TState] | None = None,
):
	def decorator(func: Callable[Concatenate[TState, P], Awaitable[T]], /):
		sig = inspect.signature(func)
		params = list(sig.parameters.values())

		if len(params) == 0 or params[0].name != "self":
			raise TypeError("@mutation method must have 'self' as first argument")

		return MutationProperty(
			func.__name__,
			func,
			on_success=on_success,
			on_error=on_error,
		)

	if fn:
		return decorator(fn)
	return decorator
