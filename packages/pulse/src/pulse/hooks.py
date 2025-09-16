from contextvars import ContextVar
from typing import (
    Any,
    Callable,
    Generic,
    Literal,
    Mapping,
    NoReturn,
    Optional,
    ParamSpec,
    Protocol,
    TypeVar,
    TypeVarTuple,
    cast,
    overload,
)

from pulse.context import PulseContext
from pulse.flags import IS_PRERENDERING
from pulse.reactive import Effect, EffectFn, Scope, Signal, Untrack
from pulse.reactive_extensions import ReactiveDict
from pulse.routing import RouteContext
from pulse.state import State


class RedirectInterrupt(Exception):
    def __init__(self, path: str, *, replace: bool = False):
        super().__init__(path)
        self.path = path
        self.replace = replace


class NotFoundInterrupt(Exception):
    pass


# Sentinel used to represent an unspecified key
MISSING: Any = object()


class SetupState:
    value: Any
    initialized: bool
    args: list
    kwargs: dict
    effects: list[Effect]
    key: Any

    def __init__(self, value: Any = None, initialized: bool = False):
        self.value = value
        self.initialized = initialized
        self.args = []
        self.kwargs = {}
        self.effects = []
        self.key = MISSING


class StatesHookState:
    states: tuple[State, ...]
    key: Any
    initialized: bool

    def __init__(self) -> None:
        self.states = ()
        self.key = MISSING
        self.initialized = False


class EffectsHookState:
    effects: tuple[Effect, ...]
    key: Any
    initialized: bool

    def __init__(
        self,
    ) -> None:
        self.effects = ()
        self.key = MISSING
        self.initialized = False


class HookCalls:
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


class StableEntry:
    def __init__(self, value: Any, wrapper: Callable):
        self.value = value
        self.wrapper = wrapper


class HookState:
    setup: SetupState
    states: StatesHookState
    effects: EffectsHookState
    called: HookCalls
    render_count: int
    stable_registry: dict[str, StableEntry]
    pending_setup_key: Any

    def __init__(self):
        self.setup = SetupState()
        self.states = StatesHookState()
        self.effects = EffectsHookState()
        self.called = HookCalls()
        self.render_count = 0
        self.stable_registry = {}
        self.pending_setup_key = MISSING

    def ctx(self):
        self.called.reset()
        self.render_count += 1
        return MountHookState(self)

    def unmount(self):
        for effect in self.setup.effects:
            effect.dispose()
        for effect in self.effects.effects:
            effect.dispose()
        for state in self.states.states:
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
    # Read and clear any pending key set by setup_key()
    key = ctx.pending_setup_key
    ctx.pending_setup_key = MISSING
    # Re-run setup if a key is supplied and changed
    if state.initialized and key is not MISSING and key != state.key:
        # Dispose previous setup effects and reset tracked args/kwargs signals
        for effect in state.effects:
            effect.dispose()
        state.effects = []
        with Scope() as scope:
            state.value = init_func(*args, **kwargs)
            state.initialized = True
            state.effects = list(scope.effects)
            state.args = [Signal(x) for x in args]
            state.kwargs = {k: Signal(v) for k, v in kwargs.items()}
            state.key = key
        return state.value

    if not state.initialized:
        with Scope() as scope:
            state.value = init_func(*args, **kwargs)
            state.initialized = True
            state.effects = list(scope.effects)
            state.args = [Signal(x) for x in args]
            state.kwargs = {k: Signal(v) for k, v in kwargs.items()}
            if key is not MISSING:
                state.key = key
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
        if key is not MISSING:
            state.key = key
    return state.value


def setup_key(key: Any) -> None:
    """Set a key for the next setup() call in this component render.

    Must be invoked before setup() in the same render. If the key differs from the
    previous value, setup() will dispose its prior resources and re-run.
    """
    ctx = HOOK_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("setup_key() must be invoked during component render")
    if ctx.called.setup:
        raise RuntimeError("setup_key() must be called before setup() in a render")
    ctx.pending_setup_key = key


# -----------------------------------------------------
# Ugly types, sorry, no other way to do this in Python
# -----------------------------------------------------
# The covariant=True is necessary for the global_state definition below
S = TypeVar("S", covariant=True, bound=State)
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
def states(s1: S1 | Callable[[], S1], /, *, key: Any = ...) -> S1: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def states(
    s1: S1 | Callable[[], S1], s2: S2 | Callable[[], S2], /, *, key: Any = ...
) -> tuple[S1, S2]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    /,
    *,
    key: Any = ...,
) -> tuple[S1, S2, S3]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    /,
    *,
    key: Any = ...,
) -> tuple[S1, S2, S3, S4]: ...
@overload
def states(
    s1: S1 | Callable[[], S1],
    s2: S2 | Callable[[], S2],
    s3: S3 | Callable[[], S3],
    s4: S4 | Callable[[], S4],
    s5: S5 | Callable[[], S5],
    /,
    *,
    key: Any = ...,
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
    *,
    key: Any = ...,
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
    *,
    key: Any = ...,
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
    *,
    key: Any = ...,
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
    *,
    key: Any = ...,
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
    *,
    key: Any = ...,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]: ...


@overload
def states(*args: S | Callable[[], S], key: Any = ...) -> tuple[S, ...]: ...


def states(*args: State | Callable[[], State], key: Any = MISSING):
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

    if not ctx.states.initialized:
        states: list[State] = []
        for arg in args:
            state_instance = arg() if callable(arg) else arg
            states.append(state_instance)
        ctx.states.states = tuple(states)
        ctx.states.key = key
        ctx.states.initialized = True
    else:
        # If key supplied and changed, dispose all previous states and recreate
        if key is not MISSING and key != ctx.states.key:
            for s in ctx.states.states:
                s.dispose()
            new_states: list[State] = []
            for arg in args:
                state_instance = arg() if callable(arg) else arg
                new_states.append(state_instance)
            ctx.states.states = tuple(new_states)
            ctx.states.key = key
        else:
            # As before, dispose any instances passed positionally on subsequent renders
            for arg in args:
                if isinstance(arg, State):
                    arg.dispose()

    if len(ctx.states.states) == 1:
        return ctx.states.states[0]
    else:
        return ctx.states.states


def effects(
    *fns: EffectFn,
    on_error: Callable[[Exception], None] | None = None,
    key: Any = MISSING,
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
    if not ctx.effects.initialized:
        ctx.effects.initialized = True
        with Untrack():
            effects = []
            for fn in fns:
                if not callable(fn):
                    raise ValueError(
                        "Only pass functions or callabGle objects to `ps.effects`"
                    )
                effects.append(Effect(fn, name=fn.__name__, on_error=on_error))
            ctx.effects.effects = tuple(effects)
            ctx.effects.key = key
    else:
        # If key supplied and changed, dispose old effects and recreate
        if key is not MISSING and key != ctx.effects.key:
            for eff in ctx.effects.effects:
                eff.dispose()
            with Untrack():
                effects = []
                for fn in fns:
                    if not callable(fn):
                        raise ValueError(
                            "Only pass functions or callabGle objects to `ps.effects`"
                        )
                    effects.append(Effect(fn, name=fn.__name__, on_error=on_error))
                ctx.effects.effects = tuple(effects)
                ctx.effects.key = key


P = ParamSpec("P")
R = TypeVar("R")


@overload
def stable(key: str) -> Any: ...
@overload
def stable(key: str, value: Callable[P, R]) -> Callable[P, R]: ...
@overload
def stable(key: str, value: T) -> Callable[[], T]: ...
def stable(key: str, value: Any = MISSING):
    # Implement:
    # - Just the key -> return the corresponding value (or raise if it doesn't exist)
    # - Key + callable -> wrap the callable in a passthrough that has the same signature but always calls the latest passed in version of the callable
    # - Key + value -> return a callable that always returns the latest passed in value
    ctx = HOOK_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("stable() must be invoked during component render")

    registry = ctx.stable_registry

    # When a value is provided, (re)register and return a stable wrapper
    if value is not MISSING:
        entry = registry.get(key)
        if entry is None:

            def wrapper(*args: Any, **kwargs: Any):
                current = registry[key].value
                if callable(current):
                    return current(*args, **kwargs)
                return current

            entry = StableEntry(value, wrapper)
            registry[key] = entry
        else:
            entry.value = value
        return entry.wrapper

    # Key-only: return existing stable wrapper
    entry = registry.get(key)
    if entry is None:
        raise KeyError(f"stable(): no value registered for key '{key}'")
    return entry.wrapper


def route() -> RouteContext:
    ctx = PulseContext.get()
    if not ctx or not ctx.route:
        raise RuntimeError(
            "`pulse.router` can only be called within a component during rendering."
        )
    return ctx.route


def session() -> ReactiveDict[str, Any]:
    """Return the shared per-user session ReactiveDict.

    Available during prerender, rendering, callbacks, middleware, and API routes.
    """

    ctx = PulseContext.get()
    if not ctx.session:
        raise RuntimeError("Could not resolve user session")
    return ctx.session.data


def session_id() -> str:
    ctx = PulseContext.get()
    if not ctx.session:
        raise RuntimeError("Could not resolve user session")
    return ctx.session.sid


def websocket_id() -> str:
    ctx = PulseContext.get()
    if not ctx.render:
        raise RuntimeError("Could not resolve WebSocket session")
    return ctx.render.id


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
    ctx = PulseContext.get()
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
    ctx = PulseContext.get()
    if ctx.session is None:
        raise RuntimeError("Could not resolve the user session")
    ctx.session.set_cookie(
        name=name,
        value=value,
        domain=domain,
        secure=secure,
        samesite=samesite,
        max_age_seconds=max_age_seconds,
    )


def navigate(path: str, *, replace: bool = False) -> None:
    """Instruct the client to navigate to a new path for the current route tree.

    Non-blocking; sends a server message to the client to perform SPA navigation.
    """

    ctx = PulseContext.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError("navigate() must be invoked inside a Pulse callback context")
    # Emit navigate_to once; client will handle redirect at app-level
    ctx.render.send({"type": "navigate_to", "path": path, "replace": replace})


def redirect(path: str, *, replace: bool = False) -> NoReturn:
    """Interrupt rendering to perform a redirect/navigation.

    - During prerender: surfaces to the server to return an HTTP redirect.
    - During live render: caught by the render loop to send a navigate message
      instead of emitting VDOM updates.

    Must be invoked during component rendering.
    """
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError("redirect() must be invoked during component render")
    raise RedirectInterrupt(path, replace=replace)


def not_found() -> NoReturn:
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError("not_found() must be invoked during component render")
    raise NotFoundInterrupt()


def is_prerendering():
    return IS_PRERENDERING.get()


# -----------------------------------------------------
# Server/Client addressing hooks
# -----------------------------------------------------


def server_address() -> str:
    """Return the base server address for the current session.

    Example return values: "http://127.0.0.1:8000", "https://example.com:443"
    """

    ctx = PulseContext.get()
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

    ctx = PulseContext.get()
    if ctx.render is None:
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
        ctx = PulseContext.get()
        if ctx is None or ctx.render is None:
            raise RuntimeError(
                "ps.global_state must be used inside a Pulse render/callback context"
            )
        return cast(
            S, ctx.render.get_global_state(base_key, lambda: mk(*args, **kwargs))
        )

    return accessor
