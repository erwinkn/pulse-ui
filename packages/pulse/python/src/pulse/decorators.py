# Separate file from reactive.py due to needing to import from state too

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast, overload

from pulse.hooks.core import HOOK_CONTEXT
from pulse.hooks.effects import inline_effect_hook
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
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
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
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
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
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
) -> EffectBuilder: ...


def effect(
	fn: Callable[..., Any] | None = None,
	*,
	name: str | None = None,
	immediate: bool = False,
	lazy: bool = False,
	on_error: Callable[[Exception], None] | None = None,
	deps: list[Signal[Any] | Computed[Any]] | None = None,
	update_deps: bool | None = None,
	interval: float | None = None,
	key: str | None = None,
):
	# The type checker is not happy if I don't specify the `/` here.
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
				name=name,
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
					name=name or func.__name__,
					lazy=lazy,
					on_error=on_error,
					deps=deps,
					update_deps=update_deps,
					interval=interval,
				)
			return Effect(
				func,  # type: ignore[arg-type]
				name=name or func.__name__,
				immediate=immediate,
				lazy=lazy,
				on_error=on_error,
				deps=deps,
				update_deps=update_deps,
				interval=interval,
			)

		if ctx is None:
			# Not in component - create standalone effect (current behavior)
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
		identity = (func.__qualname__, func.__code__, caller.f_code)

		state = inline_effect_hook()
		return state.get_or_create(cast(Any, identity), key, create_effect)

	if fn is not None:
		return decorator(fn)
	return decorator
