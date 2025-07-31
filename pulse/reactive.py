# Global registry for init functions per route
from typing import Any, Callable, ParamSpec, TypeVar
from .route import current_active_route

P = ParamSpec("P")
T = TypeVar("T")
ROUTE_STATES: dict[str, Any] = {}


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
    route = current_active_route()
    if route is None:
        raise RuntimeError("pulse.init() can only be called during route rendering")

    route_path = route.path

    # Initialize route registry if needed
    if route_path not in ROUTE_STATES:
        ROUTE_STATES[route_path] = init_func(*args, **kwargs)

    return ROUTE_STATES[route_path]
