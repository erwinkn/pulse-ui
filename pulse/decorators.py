# Separate file from reactive.py due to needing to import from state too

from typing import Callable, Optional, TypeVar, overload
from pulse.state import State, ComputedProperty, StateEffect
from pulse.reactive import Computed, Effect, EffectCleanup, EffectFn
import inspect
from pulse.query import QueryProperty


T = TypeVar("T")
TState = TypeVar("TState", bound=State)


# -> @ps.computed The chalenge is:
# - We want to turn regular functions with no arguments into a Computed object
# - We want to turn state methods into a ComputedProperty (which wraps a
#   Computed, but gives it access to the State object).
@overload
def computed(fn: Callable[[], T], *, name: Optional[str] = None) -> Computed[T]: ...
@overload
def computed(
    fn: Callable[[TState], T], *, name: Optional[str] = None
) -> ComputedProperty[T]: ...
@overload
def computed(
    fn: None = None, *, name: Optional[str] = None
) -> Callable[[Callable[[], T]], Computed[T]]: ...


def computed(fn: Optional[Callable] = None, *, name: Optional[str] = None):
    # The type checker is not happy if I don't specify the `/` here.
    def decorator(fn: Callable, /):
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


@overload
def effect(
    fn: EffectFn,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> Effect: ...
# In practice this overload returns a StateEffect, but it gets converted into an
# Effect at state instantiation.
@overload
def effect(
    fn: Callable[[TState], None] | Callable[[TState], EffectCleanup],
) -> Effect: ...
@overload
def effect(
    fn: None = None,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> Callable[[EffectFn], Effect]: ...


def effect(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
):
    # The type checker is not happy if I don't specify the `/` here.
    def decorator(func: Callable, /):
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) == 1 and params[0].name == "self":
            return StateEffect(func, on_error=on_error)

        if len(params) > 0:
            raise TypeError(
                f"@effect: Function '{func.__name__}' must take no arguments or a single 'self' argument"
            )

        # This is a standalone effect function. Create the Effect object.
        return Effect(
            func,
            name=name or func.__name__,
            immediate=immediate,
            lazy=lazy,
            on_error=on_error,
        )

    if fn:
        return decorator(fn)
    return decorator


# -----------------
# Query decorator
# -----------------
@overload
def query(
    fn: Callable[[TState], T], *, keep_alive: bool = False
) -> QueryProperty[T]: ...
@overload
def query(
    fn: None = None, *, keep_alive: bool = False
) -> Callable[[Callable[[State], T]], QueryProperty[T]]: ...


def query(fn: Optional[Callable] = None, *, keep_alive: bool = False):
    def decorator(func: Callable, /):
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        # Only state-method form supported for now (single 'self')
        if not (len(params) == 1 and params[0].name == "self"):
            raise TypeError("@query currently only supports state methods (self)")
        return QueryProperty(func.__name__, func, keep_alive=keep_alive)

    if fn:
        return decorator(fn)
    return decorator
