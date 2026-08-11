# Separate file from reactive.py due to needing to import from state too

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast, overload

from pulse.hooks.core import HOOK_CONTEXT
from pulse.hooks.effects import effect_state
from pulse.hooks.state import collect_component_identity
from pulse.reactive import (
	AsyncEffect,
	AsyncEffectFn,
	Computed,
	Effect,
	EffectCleanup,
	EffectFn,
	Signal,
)
from pulse.resources import current_resource_scope
from pulse.state.property import ComputedProperty, StateEffect
from pulse.state.state import State

T = TypeVar("T")
TState = TypeVar("TState", bound=State)
P = ParamSpec("P")


@overload
def computed(fn: Callable[[], T]) -> Computed[T]: ...
@overload
def computed(fn: Callable[[TState], T]) -> ComputedProperty[T]: ...


def computed(fn: Callable[..., Any]) -> Computed[T] | ComputedProperty[T]:
	"""
	Decorator for computed (derived) properties.

	Creates a cached, reactive value that automatically recalculates when its
	dependencies change. The computed tracks which Signals/Computeds are read
	during execution and subscribes to them.

	Can be used in two ways:
	1. On a State method (with single `self` argument) - creates a ComputedProperty
	2. As a standalone function (with no arguments) - creates a Computed

	Args:
		fn: The function to compute the value. Must take no arguments (standalone) or only `self` (State method).

	Returns:
		Computed or ComputedProperty depending on usage.

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
	"""
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
	return Computed(fn, name=fn.__name__)


StateEffectFn = Callable[[TState], EffectCleanup | None]
AsyncStateEffectFn = Callable[[TState], Awaitable[EffectCleanup | None]]


class EffectBuilder(Protocol):
	@overload
	def __call__(self, fn: EffectFn) -> Effect: ...
	@overload
	def __call__(self, fn: AsyncEffectFn) -> AsyncEffect: ...
	@overload
	def __call__(
		self, fn: StateEffectFn[Any] | AsyncStateEffectFn[Any]
	) -> StateEffect[Any]: ...
	def __call__(
		self,
		fn: EffectFn | StateEffectFn[Any] | AsyncEffectFn | AsyncStateEffectFn[Any],
	) -> Effect | AsyncEffect | StateEffect[Any]: ...


@overload
def effect(
	fn: EffectFn,
	*,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
) -> Effect: ...


@overload
def effect(
	fn: AsyncEffectFn,
	*,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
) -> AsyncEffect: ...
@overload
def effect(fn: StateEffectFn[Any] | AsyncStateEffectFn[Any]) -> StateEffect[Any]: ...
@overload
def effect(
	fn: None = None,
	*,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
) -> EffectBuilder: ...


def effect(
	fn: Callable[..., Any] | None = None,
	*,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
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
		immediate: If True, run synchronously when scheduled instead of batching.
		        Only valid for sync effects.
		lazy: If True, don't run on creation; wait for first dependency change.
		on_error: Callback invoked if the effect throws an exception.
		deps: Explicit list of dependencies. If provided, auto-tracking is disabled
		        and the effect only re-runs when these specific dependencies change.
		interval: Re-run interval in seconds. Creates a polling effect that runs
		        periodically regardless of dependency changes.

	Returns:
		Effect, AsyncEffect, or StateEffect depending on usage.

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

		# Disallow immediate + async
		if immediate and inspect.iscoroutinefunction(func):
			raise ValueError("Async effects cannot have immediate=True")

		# State method - unchanged behavior
		if len(params) == 1 and params[0].name == "self":
			return StateEffect(
				func,
				immediate=immediate,
				lazy=lazy,
				on_error=on_error,
				deps=deps,
				update_deps=update_deps,
				interval=interval,
			)

		# Allow params with defaults (used for variable binding in loops)
		# Reject only if there are required params (no default)
		required_params = [p for p in params if p.default is inspect.Parameter.empty]
		if required_params:
			raise TypeError(
				f"@effect: Function '{func.__name__}' must take no arguments, a single 'self' argument, "
				+ "or only arguments with defaults (for variable binding)"
			)

		# Check if we're in a hook context (component render)
		ctx = HOOK_CONTEXT.get()

		def create_effect() -> Effect | AsyncEffect:
			if inspect.iscoroutinefunction(func):
				return AsyncEffect(
					func,  # type: ignore[arg-type]
					name=func.__name__,
					lazy=lazy,
					on_error=on_error,
					deps=deps,
					update_deps=update_deps,
					interval=interval,
				)
			return Effect(
				func,  # type: ignore[arg-type]
				name=func.__name__,
				immediate=immediate,
				lazy=lazy,
				on_error=on_error,
				deps=deps,
				update_deps=update_deps,
				interval=interval,
			)

		if ctx is None or current_resource_scope() is not None:
			# Outside a component, or owned by a one-time initializer.
			return create_effect()

		# In component render - use inline caching

		# Get the frame where the decorator was applied.
		# When called as `@ps.effect` (no parens), the call stack is:
		#   decorator -> effect -> component
		# When called as `@ps.effect(...)` (with parens), the stack is:
		#   decorator -> component
		# We detect which case by checking if the immediate caller is effect().
		frame = inspect.currentframe()
		assert frame is not None
		caller = frame.f_back
		assert caller is not None
		# If the immediate caller is the effect function itself, go back one more
		if (
			caller.f_code.co_name == "effect"
			and "decorators" in caller.f_code.co_filename
		):
			caller = caller.f_back
			assert caller is not None
		if key is None:
			identity = collect_component_identity(caller)
		else:
			identity = key

		state = effect_state()
		return state.get_or_create(cast(Any, identity), key, create_effect)

	if fn is not None:
		return decorator(fn)
	return decorator
