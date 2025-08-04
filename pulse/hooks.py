from contextvars import ContextVar
from typing import Any, Callable, NamedTuple, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class SetupState:
    value: Any
    last_access: int
    initialized: bool

    def __init__(
        self, value: Any = None, last_access: int = 0, initialized: bool = False
    ):
        self.value = value
        self.last_access = last_access
        self.initialized = initialized


class ReactiveState:
    setup: SetupState
    render_count: int

    def __init__(self, setup: SetupState, render_count) -> None:
        self.render_count = render_count
        self.setup = setup

    @staticmethod
    def create():
        return ReactiveState(
            SetupState(value=None, last_access=0, initialized=False), render_count=0
        )

    def start_render(self):
        new_state = ReactiveState(self.setup, render_count=self.render_count + 1)
        # Reset last_access for the new render cycle
        new_state.setup.last_access = 0
        return new_state

    def __enter__(self):
        self._token = REACTIVE_STATE.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        REACTIVE_STATE.reset(self._token)


REACTIVE_STATE: ContextVar[ReactiveState | None] = ContextVar(
    "pulse_reactive_state", default=None
)


def init(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    reactive_state = REACTIVE_STATE.get()
    if reactive_state is None:
        raise RuntimeError("Cannot call `pulse.init` outside rendering")
    state = reactive_state.setup
    if not state.initialized:
        state.value = init_func(*args, **kwargs)
        state.initialized = True
    if state.last_access >= reactive_state.render_count:
        raise RuntimeError(
            "Cannot call `pulse.init` can only be called once per component render"
        )
    state.last_access += 1
    return state.value
