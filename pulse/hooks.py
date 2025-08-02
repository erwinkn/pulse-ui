from typing import Callable, ParamSpec, TypeVar
from .reactive import REACTIVE_CONTEXT

P = ParamSpec("P")
T = TypeVar("T")


def init(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """
    Initialize state or other objects that should persist across re-renders.

    The init function is only called once per route. Subsequent calls return
    the same cached result.

    Args:
        init_func: Function that returns the object to initialize

    Returns:
        The initialized object (same instance across re-renders)
    """
    ctx = REACTIVE_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("pulse.init() can only be called during rendering")

    if not ctx.init.initialized:
        ctx.init.state = init_func(*args, **kwargs)
        ctx.init.initialized = True
    if ctx.init.last_call == ctx.counter:
        raise RuntimeError("pulse.init() can only be called once per component")
    ctx.init.last_call = ctx.counter
    return ctx.init.state


def router(): ...
