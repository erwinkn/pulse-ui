# Separate file from reactive.py due to needing to import from state too

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, overload

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
	"""
	Decorator for computed (derived) properties.

	Creates a cached, reactive value that automatically recalculates when its
	dependencies change. The computed tracks which Signals/Computeds are read
	during execution and subscribes to them.

	Can be used in two ways:
	1. On a State method (with single `self` argument) - creates a ComputedProperty
	2. As a standalone function (with no arguments) - creates a Computed

	Args:
		fn: The function to compute the value. Must take no arguments (standalone)
		    or only `self` (State method).
		name: Optional debug name for the computed. Defaults to the function name.

	Returns:
		ComputedProperty[T]: When decorating a State method.
		Computed[T]: When decorating a standalone function.

	Raises:
		TypeError: If the function takes arguments other than `self`.

	Example:
		On a State method:

		    class MyState(ps.State):
		        count: int = 0

		        @ps.computed
		        def doubled(self):
		            return self.count * 2

		As a standalone computed:

		    signal = Signal(5)

		    @ps.computed
		    def doubled():
		        return signal() * 2

		With explicit name:

		    @ps.computed(name="my_computed")
		    def doubled(self):
		        return self.count * 2
	"""

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
	interval: float | None = None,
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
	interval: float | None = None,
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
	interval: float | None = None,
) -> EffectBuilder: ...


def effect(
	fn: Callable[..., Any] | None = None,
	*,
	name: str | None = None,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
	interval: float | None = None,
):
	"""
	Decorator for side effects that run when dependencies change.

	Creates an effect that automatically re-runs when any of its tracked
	dependencies change. Dependencies are automatically tracked by observing
	which Signals/Computeds are read during execution.

	Can be used in two ways:
	1. On a State method (with single `self` argument) - creates a StateEffect
	2. As a standalone function (with no arguments) - creates an Effect

	Supports both sync and async functions. Async effects cannot use `immediate=True`.

	Args:
		fn: The effect function. Must take no arguments (standalone) or only
		    `self` (State method). Can return a cleanup function.
		name: Optional debug name. Defaults to "ClassName.method_name" or function name.
		immediate: If True, run synchronously when scheduled instead of batching.
		    Only valid for sync effects.
		lazy: If True, don't run on creation; wait for first dependency change.
		on_error: Callback invoked if the effect throws an exception.
		deps: Explicit list of dependencies. If provided, auto-tracking is disabled
		    and the effect only re-runs when these specific dependencies change.
		interval: Re-run interval in seconds. Creates a polling effect that runs
		    periodically regardless of dependency changes.

	Returns:
		Effect: For sync standalone functions.
		AsyncEffect: For async standalone functions.
		StateEffect: For State methods (converted to Effect at instantiation).

	Raises:
		TypeError: If the function takes arguments other than `self`.
		ValueError: If `immediate=True` is used with an async function.

	Example:
		State method effect:

		    class MyState(ps.State):
		        count: int = 0

		        @ps.effect
		        def log_changes(self):
		            print(f"Count is {self.count}")

		Async effect:

		    class MyState(ps.State):
		        query: str = ""

		        @ps.effect
		        async def fetch_data(self):
		            data = await api.fetch(self.query)
		            self.data = data

		Effect with cleanup:

		    @ps.effect
		    def subscribe(self):
		        unsub = event_bus.subscribe(self.handle)
		        return unsub  # Called before next run or on dispose

		Polling effect:

		    @ps.effect(interval=5.0)
		    async def poll_status(self):
		        self.status = await api.get_status()
	"""

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
				interval=interval,
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
				interval=interval,
			)
		return Effect(
			func,  # type: ignore[arg-type]
			name=name or func.__name__,
			immediate=immediate,
			lazy=lazy,
			on_error=on_error,
			deps=deps,
			interval=interval,
		)

	if fn:
		return decorator(fn)
	return decorator
