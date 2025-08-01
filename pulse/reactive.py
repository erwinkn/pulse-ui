from contextvars import ContextVar
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, ParamSpec, TypeVar

# Avoid circular import -> we can only reference State in a quoted type hint
if TYPE_CHECKING:
    from pulse.state import State


class InitState:
    def __init__(self, value: Any, initialized: bool, last_call: int):
        self.state = value
        self.initialized = initialized
        self.last_call = last_call

    @staticmethod
    def empty():
        return InitState(value=None, initialized=False, last_call=-1)


class UpdateScheduler:
    def __init__(self) -> None:
        self.updates: set[Callable] = set()

    def schedule(self, update: Callable):
        self.updates.add(update)

    def flush(self):
        for fn in self.updates:
            try:
                fn()
            except Exception as e:
                logging.error(f"Error: {e}")
        self.updates.clear()

    def __enter__(self):
        self._token = UPDATE_SCHEDULER.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        UPDATE_SCHEDULER.reset(self._token)


UPDATE_SCHEDULER: ContextVar[UpdateScheduler | None] = ContextVar(
    "pulse-update-scheduler", default=None
)


class ReactiveContext:
    """
    Context object that tracks state access during rendering.
    """

    # Map of state instances to the properties accessed
    initialized: bool
    init: InitState
    client_states: "dict[State, set[str]]"
    # Tracks the number of rerenders
    counter: int

    def __init__(
        self,
        initialized: bool = False,
        init: Optional[InitState] = None,
        client_states: Optional[dict] = None,
        counter: int = 0,
    ) -> None:
        self.initialized = initialized
        self.init = init if init is not None else InitState.empty()
        self.client_states = client_states if client_states is not None else {}
        self.counter = counter

    @staticmethod
    def empty():
        return ReactiveContext(
            initialized=False,
            init=InitState.empty(),
            client_states={},
            counter=0,
        )

    def next_render(self):
        return ReactiveContext(
            initialized=self.initialized,
            init=self.init,
            client_states={},
            counter=self.counter + 1,
        )

    def track_state_access(self, state: "State", property_name: str):
        """Track that a state property was accessed during rendering."""
        if state not in self.client_states:
            self.client_states[state] = set()

        self.client_states[state].add(property_name)

    def __enter__(self):
        """Enter the context manager - set this as the global render context."""
        self._reset_token = RENDER_CONTEXT.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager - restore the previous render context."""
        RENDER_CONTEXT.reset(self._reset_token)
        return False


RENDER_CONTEXT: ContextVar[Optional[ReactiveContext]] = ContextVar(
    "pulse-render-context", default=None
)


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
    ctx = RENDER_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("pulse.init() can only be called during rendering")

    if not ctx.init.initialized:
        ctx.init.state = init_func(*args, **kwargs)
        ctx.init.initialized = True
    if ctx.init.last_call == ctx.counter:
        raise RuntimeError("pulse.init() can only be called once per component")
    ctx.init.last_call = ctx.counter
    return ctx.init.state
