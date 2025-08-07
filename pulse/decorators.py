# Separate file from reactive.py due to needing to import from state too

from typing import Callable, Optional, TypeVar, overload
from pulse.state import State, ComputedProperty, StateEffect
from pulse.reactive import Computed, Effect, EffectCleanup, EffectFn
import inspect


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
    fn: EffectFn, *, name: Optional[str] = None, immediate: bool = False, lazy=False
) -> Effect: ...
@overload
def effect(
    fn: Callable[[TState], None] | Callable[[TState], EffectCleanup],
) -> StateEffect: ...
@overload
def effect(
    fn: None = None, *, name: Optional[str] = None, immediate: bool = False, lazy=False
) -> Callable[[EffectFn], Effect]: ...


def effect(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy=False,
):
    # The type checker is not happy if I don't specify the `/` here.
    def decorator(func: Callable, /):
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) == 1 and params[0].name == "self":
            return StateEffect(func, immediate=immediate)

        if len(params) > 0:
            raise TypeError(
                f"@effect: Function '{func.__name__}' must take no arguments or a single 'self' argument"
            )

        # This is a standalone effect function. Create the Effect object.
        return Effect(func, name=name or func.__name__, immediate=immediate, lazy=lazy)

    if fn:
        return decorator(fn)
    return decorator
