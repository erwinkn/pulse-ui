from contextvars import ContextVar, Token
from typing import (
    Any,
    Callable,
    Mapping,
    NamedTuple,
    Optional,
    ParamSpec,
    TypeVar,
    TypeVarTuple,
    Unpack,
    overload,
)

from pulse.diff import VDOM
from pulse.messages import RouteInfo
from pulse.reactive import Effect, EffectFn, Scope, Signal, Untrack, REACTIVE_CONTEXT
from pulse.reactive_extensions import ReactiveDict
from pulse.routing import Layout, Route
from pulse.state import State
from pulse.vdom import Callbacks, Node, NodeTree


class SetupState:
    value: Any
    initialized: bool
    args: list[Signal]
    kwargs: dict[str, Signal]
    effects: list[Effect]

    def __init__(self, value: Any = None, initialized: bool = False):
        self.value = value
        self.initialized = initialized
        self.args = []
        self.kwargs = {}
        self.effects = []


class HookCalled:
    def __init__(self) -> None:
        self.reset()

    def reset(self):
        self.setup = False
        self.states = False
        self.effects = False


class MountHookState:
    def __init__(self, hooks: "HookState") -> None:
        self.hooks = hooks
        self._token = None

    def __enter__(self):
        self._token = HOOK_CONTEXT.set(self.hooks)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            HOOK_CONTEXT.reset(self._token)


class HookState:
    setup: SetupState
    states: tuple[State, ...]
    effects: tuple[Effect, ...]
    called: HookCalled
    render_count: int

    def __init__(self):
        self.setup = SetupState()
        self.effects = ()
        self.states = ()
        self.called = HookCalled()
        self.render_count = 0

    def ctx(self):
        self.called.reset()
        self.render_count += 1
        return MountHookState(self)

    def unmount(self):
        for effect in self.setup.effects:
            effect.dispose()
        for effect in self.effects:
            effect.dispose()
        for state in self.states:
            for effect in state.effects():
                effect.dispose()


HOOK_CONTEXT: ContextVar[HookState | None] = ContextVar(
    "pulse_hook_context", default=None
)


P = ParamSpec("P")
T = TypeVar("T")


def setup(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    ctx = HOOK_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("Cannot call `pulse.init` hook without a hook context.")
    if ctx.called.setup:
        raise RuntimeError(
            "Cannot call `pulse.init` can only be called once per component render"
        )
    state = ctx.setup
    if not state.initialized:
        with Scope() as scope:
            state.value = init_func(*args, **kwargs)
            state.initialized = True
            state.effects = list(scope.effects)
            state.args = [Signal(x) for x in args]
            state.kwargs = {k: Signal(v) for k, v in kwargs.items()}
    else:
        if len(args) != len(state.args):
            raise RuntimeError(
                "Number of positional arguments passed to `pulse.setup` changed. Make sure you always call `pulse.setup` with the same number of positional arguments and the same keyword arguments."
            )
        if kwargs.keys() != state.kwargs.keys():
            new_keys = kwargs.keys() - state.kwargs.keys()
            missing_keys = state.kwargs.keys() - kwargs.keys()
            raise RuntimeError(
                f"Keyword arguments passed to `pulse.setup` changed. New arguments: {list(new_keys)}. Missing arguments: {list(missing_keys)}. Make sure you always call `pulse.setup` with the same number of positional arguments and the same keyword arguments."
            )
        for i, arg in enumerate(args):
            state.args[i].write(arg)
        for k, v in kwargs.items():
            state.kwargs[k].write(v)
    return state.value


# -----------------------------------------------------
# Ugly types, sorry, no other way to do this in Python
# -----------------------------------------------------
S1 = TypeVar("S1", bound=State)
S2 = TypeVar("S2", bound=State)
S3 = TypeVar("S3", bound=State)
S4 = TypeVar("S4", bound=State)
S5 = TypeVar("S5", bound=State)
S6 = TypeVar("S6", bound=State)
S7 = TypeVar("S7", bound=State)
S8 = TypeVar("S8", bound=State)
S9 = TypeVar("S9", bound=State)
S10 = TypeVar("S10", bound=State)


Ts = TypeVarTuple("Ts")


@overload
def states(*args: Unpack[tuple[S1 | Callable[[], S1]]]) -> S1: ...
@overload
def states(
    *args: Unpack[tuple[S1 | Callable[[], S1], S2 | Callable[[], S2]]],
) -> tuple[S1, S2]: ...
@overload
def states(
    *args: Unpack[
        tuple[S1 | Callable[[], S1], S2 | Callable[[], S2], S3 | Callable[[], S3]]
    ],
) -> tuple[S1, S2, S3]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
        ]
    ],
) -> tuple[S1, S2, S3, S4]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
            S5 | Callable[[], S5],
        ]
    ],
) -> tuple[S1, S2, S3, S4, S5]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
            S5 | Callable[[], S5],
            S6 | Callable[[], S6],
        ]
    ],
) -> tuple[S1, S2, S3, S4, S5, S6]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
            S5 | Callable[[], S5],
            S6 | Callable[[], S6],
            S7 | Callable[[], S7],
        ]
    ],
) -> tuple[S1, S2, S3, S4, S5, S6, S7]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
            S5 | Callable[[], S5],
            S6 | Callable[[], S6],
            S7 | Callable[[], S7],
            S8 | Callable[[], S8],
        ]
    ],
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
            S5 | Callable[[], S5],
            S6 | Callable[[], S6],
            S7 | Callable[[], S7],
            S8 | Callable[[], S8],
            S9 | Callable[[], S9],
        ]
    ],
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9]: ...
@overload
def states(
    *args: Unpack[
        tuple[
            S1 | Callable[[], S1],
            S2 | Callable[[], S2],
            S3 | Callable[[], S3],
            S4 | Callable[[], S4],
            S5 | Callable[[], S5],
            S6 | Callable[[], S6],
            S7 | Callable[[], S7],
            S8 | Callable[[], S8],
            S9 | Callable[[], S9],
            S10 | Callable[[], S10],
        ]
    ],
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]: ...


@overload
def states(*args: S1 | Callable[[], S1]) -> tuple[S1, ...]: ...


def states(*args: State | Callable[[], State]):
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.states` can only be called within a component, during rendering."
        )

    if ctx.render_count == 1:
        states: list[State] = []
        for arg in args:
            state_instance = arg() if callable(arg) else arg
            states.append(state_instance)
        ctx.states = tuple(states)
    else:
        for arg in args:
            if isinstance(arg, State):
                arg.dispose()

    if len(ctx.states) == 1:
        return ctx.states[0]
    else:
        return ctx.states


def effects(*fns: EffectFn) -> None:
    # Assumption: RenderContext will set up a render context and a batch before
    # rendering. The batch ensures the effects run *after* rendering.
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.states` can only be called within a component, during rendering."
        )

    # Remove the effects passed here from the batch, ensuring they only run on mount
    if ctx.render_count == 1:
        with Untrack():
            effects = []
            for fn in fns:
                if not callable(fn):
                    raise ValueError(
                        "Only pass functions or callable objects to `ps.effects`"
                    )
                effects.append(Effect(fn, name=fn.__name__))
            ctx.effects = tuple(effects)


class Router(State):
    pathname: str
    hash: str
    query: str
    queryParams: dict[str, str]
    pathParams: dict[str, str]
    catchall: list[str]

    def __init__(self, info: RouteInfo):
        self._update_route_info(info)
        super().__init__()

    def _update_route_info(self, info: RouteInfo):
        self.pathname = info["pathname"]
        self.hash = info["hash"]
        self.query = info["query"]
        self.queryParams = info["queryParams"]
        self.pathParams = info["pathParams"]
        self.catchall = info["catchall"]


class RouteContext:
    def __init__(self, route_info: Router, session_context: ReactiveDict) -> None:
        self.route_info = route_info
        self.session_context = session_context


ROUTE_CONTEXT: ContextVar[RouteContext | None] = ContextVar(
    "pulse_route_context", default=None
)


def route_info() -> Router:
    ctx = ROUTE_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.router` can only be called within a component, during rendering."
        )
    return ctx.route_info


def session_context() -> dict[str, Any]:
    ctx = ROUTE_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.session_context` can only be called within a component, during rendering."
        )
    return ctx.session_context
