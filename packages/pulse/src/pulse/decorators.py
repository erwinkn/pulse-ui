# Separate file from reactive.py due to needing to import from state too

from typing import Any, Callable, Coroutine, Optional, Protocol, TypeVar, overload

from pulse.state import State, ComputedProperty, StateEffect
from pulse.reactive import (
    AsyncEffectFn,
    Computed,
    Effect,
    EffectCleanup,
    EffectFn,
    Signal,
    AsyncEffect,
)
import inspect
from pulse.query import QueryProperty, QueryPropertyWithInitial


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


StateEffectFn = Callable[[TState], Optional[EffectCleanup]]
AsyncStateEffectFn = Callable[[TState], Coroutine[Any, Any, Optional[EffectCleanup]]]


class EffectBuilder(Protocol):
    @overload
    def __call__(self, fn: EffectFn | StateEffectFn) -> Effect: ...
    @overload
    def __call__(self, fn: AsyncEffectFn | AsyncStateEffectFn) -> AsyncEffect: ...
    def __call__(
        self, fn: EffectFn | StateEffectFn | AsyncEffectFn | AsyncStateEffectFn
    ) -> Effect | AsyncEffect: ...


@overload
def effect(
    fn: EffectFn,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
    deps: Optional[list[Signal | Computed]] = None,
) -> Effect: ...


@overload
def effect(
    fn: AsyncEffectFn,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
    deps: Optional[list[Signal | Computed]] = None,
) -> AsyncEffect: ...
# In practice this overload returns a StateEffect, but it gets converted into an
# Effect at state instantiation.
@overload
def effect(fn: StateEffectFn) -> Effect: ...
@overload
def effect(fn: AsyncStateEffectFn) -> AsyncEffect: ...
@overload
def effect(
    fn: None = None,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
    deps: Optional[list[Signal | Computed]] = None,
) -> EffectBuilder: ...


def effect(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    immediate: bool = False,
    lazy: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
    deps: Optional[list[Signal | Computed]] = None,
):
    # The type checker is not happy if I don't specify the `/` here.
    def decorator(func: Callable, /):
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
    fn: Callable[[TState], Coroutine[Any, Any, T]],
    *,
    keep_alive: bool = False,  # noqa: F821
    keep_previous_data: bool = True,
) -> QueryProperty[T, TState]: ...
@overload
def query(
    fn: None = None, *, keep_alive: bool = False, keep_previous_data: bool = True
) -> Callable[
    [Callable[[TState], Coroutine[Any, Any, T]]], QueryProperty[T, TState]
]: ...


# When an initial value is provided, the resulting property narrows data to non-None
@overload
def query(
    fn: Callable[[TState], Coroutine[Any, Any, T]],
    *,
    keep_alive: bool = False,
    keep_previous_data: bool = True,
    initial: T,
) -> QueryPropertyWithInitial[T, TState]: ...
@overload
def query(
    fn: None = None,
    *,
    keep_alive: bool = False,
    keep_previous_data: bool = True,
    initial: T,
) -> Callable[
    [Callable[[TState], Coroutine[Any, Any, T]]], QueryPropertyWithInitial[T, TState]
]: ...


def query(
    fn: Optional[Callable[[TState], Any]] = None,
    *,
    keep_alive: bool = False,
    keep_previous_data: bool = True,
    initial: Any = None,
) -> (
    QueryProperty[T, TState]
    | QueryPropertyWithInitial[T, TState]
    | Callable[
        [Callable[[TState], Coroutine[Any, Any, T]]],
        QueryProperty[T, TState] | QueryPropertyWithInitial[T, TState],
    ]
):
    def decorator(func: Callable[[TState], Coroutine[Any, Any, T]], /):
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        # Only state-method form supported for now (single 'self')
        if not (len(params) == 1 and params[0].name == "self"):
            raise TypeError("@query currently only supports state methods (self)")
        if initial is not None:
            return QueryPropertyWithInitial(
                func.__name__,
                func,
                keep_alive=keep_alive,
                keep_previous_data=keep_previous_data,
                initial=initial,
            )
        return QueryProperty(
            func.__name__,
            func,
            keep_alive=keep_alive,
            keep_previous_data=keep_previous_data,
        )

    if fn:
        return decorator(fn)
    return decorator
