from contextvars import ContextVar
from typing import (
    Any,
    Callable,
    Generic,
    Mapping,
    ParamSpec,
    Protocol,
    TypeVar,
    TypeVarTuple,
    Unpack,
    overload,
    cast,
)

from pulse.flags import IS_PRERENDERING
from pulse.reactive import Effect, EffectFn, Scope, Signal, Untrack
from pulse.routing import ROUTE_CONTEXT, RouteContext
from pulse.state import State


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
    # Enforce single call per component render
    if ctx.called.states:
        raise RuntimeError(
            "`pulse.states` can only be called once per component render"
        )
    ctx.called.states = True

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


def effects(
    *fns: EffectFn, on_error: Callable[[Exception], None] | None = None
) -> None:
    # Assumption: RenderContext will set up a render context and a batch before
    # rendering. The batch ensures the effects run *after* rendering.
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.effects` can only be called within a component, during rendering."
        )

    # Enforce single call per component render
    if ctx.called.effects:
        raise RuntimeError(
            "`pulse.effects` can only be called once per component render"
        )
    ctx.called.effects = True

    # Remove the effects passed here from the batch, ensuring they only run on mount
    if ctx.render_count == 1:
        with Untrack():
            effects = []
            for fn in fns:
                if not callable(fn):
                    raise ValueError(
                        "Only pass functions or callabGle objects to `ps.effects`"
                    )
                effects.append(Effect(fn, name=fn.__name__, on_error=on_error))
            ctx.effects = tuple(effects)


def route_info() -> RouteContext:
    ctx = ROUTE_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.router` can only be called within a component during rendering."
        )
    return ctx


def session_context() -> dict[str, Any]:
    from pulse.session import SESSION_CONTEXT

    session = SESSION_CONTEXT.get()
    if not session:
        raise RuntimeError(
            "`pulse.session_context` can only be called within a component during rendering."
        )
    return session.context


async def call_api(
    url: str,
    *,
    method: str = "POST",
    headers: Mapping[str, str] | None = None,
    body: Any | None = None,
    credentials: str = "include",
) -> dict[str, Any]:
    """Ask the client to perform an HTTP request and await the result.

    This hides session plumbing; safe to call inside Pulse callbacks.
    """
    from pulse.session import SESSION_CONTEXT

    session = SESSION_CONTEXT.get()
    if session is None:
        raise RuntimeError("call_api() must be invoked inside a Pulse callback context")
    return await session.call_api(
        url,
        method=method,
        headers=dict(headers or {}),
        body=body,
        credentials=credentials,
    )


def navigate(path: str) -> None:
    """Instruct the client to navigate to a new path for the current route tree.

    Non-async; sends a server message to the client to perform SPA navigation.
    """
    from pulse.session import SESSION_CONTEXT

    session = SESSION_CONTEXT.get()
    if session is None:
        raise RuntimeError("navigate() must be invoked inside a Pulse callback context")
    # Emit navigate_to once; client will handle redirect at app-level
    session.notify({"type": "navigate_to", "path": path})


def is_prerendering():
    return IS_PRERENDERING.get()


# -----------------------------------------------------
# Session-local global singletons (ps.global_state)
# -----------------------------------------------------

S = TypeVar("S", covariant=True)


class GlobalStateAccessor(Protocol, Generic[S]):
    def __call__(self) -> S: ...


def global_state(
    factory: Callable[[], S] | type[S], key: str | None = None
) -> GlobalStateAccessor[S]:
    """Provider for per-session singletons.

    Usage:
        class Auth(ps.State): ...
        auth = ps.global_state(Auth)
        a = auth()  # same instance within the session

    - key None: derive a stable key from factory's module+qualname
    - future: allow passing an id in the accessor call to support cross-session sharing
    """
    from pulse.session import SESSION_CONTEXT

    if isinstance(factory, type):
        cls = factory

        def _mk() -> S:  # type: ignore[misc]
            return cast(S, cls())

        default_key = f"{cls.__module__}:{cls.__qualname__}"
        mk = _mk
    else:
        default_key = f"{factory.__module__}:{factory.__qualname__}"
        mk = factory

    base_key = key or default_key

    def accessor() -> S:
        # Default: session-local when no id provided
        session = SESSION_CONTEXT.get()
        if session is None:
            raise RuntimeError(
                "ps.global_state must be used inside a Pulse render/callback context"
            )
        return cast(S, session.get_global_state(base_key, mk))

    return accessor
