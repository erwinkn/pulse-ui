from contextvars import ContextVar
from typing import (
    Any,
    Callable,
    Generic,
    Literal,
    Mapping,
    Optional,
    ParamSpec,
    Protocol,
    TypeVar,
    TypeVarTuple,
    Unpack,
    overload,
    cast,
)

from pulse.context import PULSE_CONTEXT
from pulse.flags import IS_PRERENDERING
from pulse.reactive_extensions import ReactiveDict
from pulse.reactive import Effect, EffectFn, Scope, Signal, Untrack
from pulse.routing import RouteContext
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
S = TypeVar("S", bound=State)
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
StateOrStateLambda = State | Callable[[], State]


@overload
def states(s1: S1 | Callable[[], S1], /) -> S1: ...
@overload
def states(
    s1: S1 | Callable[[], S1], s2: S2 | Callable[[], S2], /
) -> tuple[S1, S2]: ...
@overload
def states(
    s1: S1 | Callable[[], S1], s2: S2 | Callable[[], S2], s3: S3 | Callable[[], S3], /
) -> tuple[S1, S2, S3]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    /,
) -> tuple[S1, S2, S3, S4]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    /,
) -> tuple[S1, S2, S3, S4, S5]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    s6: S6 | Callable[[], S6],
    /,
) -> tuple[S1, S2, S3, S4, S5, S6]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    s6: S6 | Callable[[], S6],
    s7: S7 | Callable[[], S7],
    /,
) -> tuple[S1, S2, S3, S4, S5, S6, S7]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    s6: S6 | Callable[[], S6],
    s7: S7 | Callable[[], S7],
    s8: S8 | Callable[[], S8],
    /,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    s6: S6 | Callable[[], S6],
    s7: S7 | Callable[[], S7],
    s8: S8 | Callable[[], S8],
    s9: S9 | Callable[[], S9],
    /,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    s6: S6 | Callable[[], S6],
    s7: S7 | Callable[[], S7],
    s8: S8 | Callable[[], S8],
    s9: S9 | Callable[[], S9],
    s10: S10 | Callable[[], S10],
    /,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]: ...


@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    s6: S6 | Callable[[], S6],
    s7: S7 | Callable[[], S7],
    s8: S8 | Callable[[], S8],
    s9: S9 | Callable[[], S9],
    s10: S10 | Callable[[], S10],
    /,
    *args: S | Callable[[], S],
) -> tuple[S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 | S, ...]: ...


# @overload
# def states(*args: S | Callable[[], S]) -> tuple[S, ...]: ...


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


def route() -> RouteContext:
    ctx = PULSE_CONTEXT.get()
    if not ctx or not ctx.route:
        raise RuntimeError(
            "`pulse.router` can only be called within a component during rendering."
        )
    return ctx.route


def session() -> ReactiveDict:
    """Return the shared per-user session ReactiveDict.

    Available during prerender, rendering, callbacks, middleware, and API routes.
    """

    ctx = PULSE_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`ps.session()` can only be called within a Pulse render/callback context."
        )
    return ctx.session


async def call_api(
    path: str,
    *,
    method: str = "POST",
    headers: Mapping[str, str] | None = None,
    body: Any | None = None,
    credentials: str = "include",
) -> dict[str, Any]:
    """Ask the client to perform an HTTP request and await the result.

    Accepts either a relative path or absolute URL; URL resolution happens in
    RenderSession.call_api using the session's server_address.
    """
    ctx = PULSE_CONTEXT.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError("call_api() must be invoked inside a Pulse callback context")

    return await ctx.render.call_api(
        path,
        method=method,
        headers=dict(headers or {}),
        body=body,
        credentials=credentials,
    )


async def set_cookie(
    name: str,
    value: str,
    domain: Optional[str] = None,
    secure: bool = True,
    samesite: Literal["lax", "strict", "none"] = "lax",
    max_age_seconds: int = 7 * 24 * 3600,
) -> None:
    """Request the client to set a cookie whose definition is stored server-side.

    Stores (name, value, options) on the server under an opaque token, then calls
    the internal endpoint with that token. Prevents client tampering with values.
    """
    ctx = PULSE_CONTEXT.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError(
            "set_cookie() must be invoked inside a Pulse callback context"
        )

    token = ctx.app.register_cookie_to_set(
        name,
        value,
        domain=domain,
        secure=secure,
        samesite=samesite,
        max_age_seconds=max_age_seconds,
    )
    path = f"/pulse/set-cookie?token={token}"
    await ctx.render.call_api(path, method="POST", credentials="include")


def navigate(path: str) -> None:
    """Instruct the client to navigate to a new path for the current route tree.

    Non-async; sends a server message to the client to perform SPA navigation.
    """

    ctx = PULSE_CONTEXT.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError("navigate() must be invoked inside a Pulse callback context")
    # Emit navigate_to once; client will handle redirect at app-level
    ctx.render.notify({"type": "navigate_to", "path": path})


def is_prerendering():
    return IS_PRERENDERING.get()


# -----------------------------------------------------
# Server/Client addressing hooks
# -----------------------------------------------------


def server_address() -> str:
    """Return the base server address for the current session.

    Example return values: "http://127.0.0.1:8000", "https://example.com:443"
    """

    ctx = PULSE_CONTEXT.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError(
            "server_address() must be called inside a Pulse render/callback context"
        )
    if not ctx.render.server_address:
        raise RuntimeError(
            "Server address unavailable. Ensure App.run_codegen/asgi_factory configured server_address."
        )
    return ctx.render.server_address


def client_address() -> str:
    """Return the best-known client address (IP or forwarded value) for this session.

    Available during prerender (HTTP request) and after websocket connect.
    """

    ctx = PULSE_CONTEXT.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError(
            "client_address() must be called inside a Pulse render/callback context"
        )
    if not ctx.render.client_address:
        raise RuntimeError(
            "Client address unavailable. It is set during prerender or socket connect."
        )
    return ctx.render.client_address


# -----------------------------------------------------
# Session-local global singletons (ps.global_state)
# -----------------------------------------------------

S = TypeVar("S", covariant=True, bound=State)


class GlobalStateAccessor(Protocol, Generic[P, S]):
    def __call__(
        self, id: str | None = None, *args: P.args, **kwargs: P.kwargs
    ) -> S: ...

    # Process-wide shared registry for cross-session instances
    # Keyed by f"{base_key}|{id}"


GLOBAL_STATES: dict[str, State] = {}


def global_state(
    factory: Callable[P, S] | type[S], key: str | None = None
) -> GlobalStateAccessor[P, S]:
    """Provider for per-session or cross-session shared state.

    Returns an accessor: `accessor(id: str | None = None, *args, **kwargs) -> S`.

    Usage:
        class Auth(ps.State): ...
        auth = ps.global_state(Auth)
        a = auth()                # per-session state (isolated per session)
        b = auth("tenant-42")     # shared state across sessions for id "tenant-42"

    Notes:
    - key None: derive a stable key from factory's module+qualname
    - id None: session-local singleton (requires session context)
      - constructor args: pass on the first call to initialize; ignored thereafter
    - id str: process-wide shared singleton for that id (cross-session)
      - constructor args: pass on the first call for that id; ignored thereafter
    """

    if isinstance(factory, type):
        cls = factory

        def _mk(*args, **kwargs) -> S:
            return cast(S, cls(*args, **kwargs))

        default_key = f"{cls.__module__}:{cls.__qualname__}"
        mk = _mk
    else:
        default_key = f"{factory.__module__}:{factory.__qualname__}"
        mk = factory

    base_key = key or default_key

    def accessor(id: str | None = None, *args: P.args, **kwargs: P.kwargs) -> S:
        # Cross-session shared instance when id is provided
        if id is not None:
            shared_key = f"{base_key}|{id}"
            inst = cast(S | None, GLOBAL_STATES.get(shared_key))
            if inst is None:
                inst = mk(*args, **kwargs)
                GLOBAL_STATES[shared_key] = inst
            return cast(S, inst)

        # Default: session-local when no id provided
        ctx = PULSE_CONTEXT.get()
        if ctx is None or ctx.render is None:
            raise RuntimeError(
                "ps.global_state must be used inside a Pulse render/callback context"
            )
        return cast(
            S, ctx.render.get_global_state(base_key, lambda: mk(*args, **kwargs))
        )

    return accessor
