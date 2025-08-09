from contextvars import ContextVar
from typing import (
    Any,
    Callable,
    NamedTuple,
    ParamSpec,
    TypeVar,
    TypeVarTuple,
    Unpack,
    overload,
)

from pulse.diff import VDOM
from pulse.messages import RouteInfo
from pulse.reactive import Effect, EffectFn, Scope, Signal, Untrack, REACTIVE_CONTEXT
from pulse.routing import Layout, Route
from pulse.state import State
from pulse.vdom import Callbacks

# Hooks we want:
# - Setup
# - State (computeds go there too)
# - Effects
# - Router (with data + navigate / push)


class RenderFlags:
    route: Route | Layout


class SetupState:
    value: Any
    last_access: int
    initialized: bool
    args: list[Signal]
    kwargs: dict[str, Signal]
    effects: list[Effect]

    def __init__(
        self, value: Any = None, last_access: int = 0, initialized: bool = False
    ):
        self.value = value
        self.last_access = last_access
        self.initialized = initialized
        self.args = []
        self.kwargs = {}
        self.effects = []


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


class HookState:
    setup: SetupState
    states: tuple[State, ...]
    effects: tuple[Effect, ...]
    router: Router
    session_context: dict[str, Any]

    def __init__(
        self,
        route_info: RouteInfo,
        session_context: dict[str, Any] | None = None,
    ):
        self.setup = SetupState()
        self.effects = ()
        self.states = ()
        self.router = Router(route_info)
        self.session_context = session_context or {}

    def dispose(self):
        for effect in self.setup.effects:
            effect.dispose()
        for effect in self.effects:
            effect.dispose()
        for state in self.states:
            for effect in state.effects():
                effect.dispose()


class RenderResult(NamedTuple):
    render_count: int
    current_vdom: VDOM | None
    new_vdom: VDOM


class RenderContext:
    route: Route | Layout
    position: str

    render_count: int
    prerendering: bool
    children: "list[RenderContext]"

    vdom: VDOM | None
    callbacks: Callbacks
    hooks: HookState
    effect: Effect | None

    def __init__(
        self,
        route: Route | Layout,
        route_info: RouteInfo,
        vdom: VDOM | None,
        prerendering: bool = False,
        position: str = "",
        session_context: dict[str, Any] | None = None,
    ):
        self.route = route
        self.position = position
        self.prerendering = prerendering
        self.vdom = vdom

        self.render_count = 0
        self.children = []

        self.callbacks = {}
        self.hooks = HookState(
            route_info=route_info,
            session_context=session_context,
        )
        self.effect = None

    def update_route_info(self, info: RouteInfo):
        self.hooks.router._update_route_info(info)

    def mount(
        self,
        on_render: Callable[[RenderResult], None],
        on_error: Callable[[Exception], None] | None = None,
    ):
        if self.effect is not None:
            raise RuntimeError("RenderContext is already mounted")

        def render_fn():
            try:
                on_render(self.render())
            except Exception as e:  # noqa: BLE001 - we want to forward any error up
                if on_error:
                    on_error(e)
                else:
                    raise

        self.effect = Effect(
            render_fn,
            immediate=True,
            name=f"{self.route.path if isinstance(self.route, Route) else 'layout'}:render:{self.position or 'root'}",
        )

    def unmount(self):
        self.hooks.dispose()
        if self.effect:
            self.effect.dispose()
            self.effect = None

    def render(self) -> RenderResult:
        self.render_count += 1
        with self:
            current_vdom = self.vdom
            new_tree = self.route.render.fn()  # type: ignore
            new_vdom, new_callbacks = new_tree.render()
            if self.prerendering:
                REACTIVE_CONTEXT.get().batch.effects = []

            self.vdom = new_vdom
            self.callbacks = new_callbacks
            return RenderResult(
                render_count=self.render_count,
                current_vdom=current_vdom,
                new_vdom=new_vdom,
            )

    @property
    def is_route(self):
        return isinstance(self.route, Route)

    @property
    def is_layout(self):
        return isinstance(self.route, Layout)

    def __enter__(self):
        self._token = RENDER_CONTEXT.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        RENDER_CONTEXT.reset(self._token)


RENDER_CONTEXT: ContextVar[RenderContext | None] = ContextVar(
    "pulse_render_context", default=None
)


P = ParamSpec("P")
T = TypeVar("T")


def setup(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    ctx = RENDER_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("Cannot call `pulse.init` outside rendering")
    state = ctx.hooks.setup
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
    if state.last_access >= ctx.render_count:
        raise RuntimeError(
            "Cannot call `pulse.init` can only be called once per component render"
        )
    state.last_access += 1
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
    ctx = RENDER_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.states` can only be called within a component, during rendering."
        )

    if ctx.render_count == 1:
        states: list[State] = []
        for arg in args:
            state_instance = arg() if callable(arg) else arg
            states.append(state_instance)
        ctx.hooks.states = tuple(states)
    else:
        for arg in args:
            if isinstance(arg, State):
                arg.dispose()

    if len(ctx.hooks.states) == 1:
        return ctx.hooks.states[0]
    else:
        return ctx.hooks.states


def effects(*fns: EffectFn) -> None:
    # Assumption: RenderContext will set up a render context and a batch before
    # rendering. The batch ensures the effects run *after* rendering.
    ctx = RENDER_CONTEXT.get()
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
            ctx.hooks.effects = tuple(effects)


def router():
    ctx = RENDER_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.router` can only be called within a component, during rendering."
        )
    return ctx.hooks.router


def session_context() -> dict[str, Any]:
    ctx = RENDER_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.session_context` can only be called within a component, during rendering."
        )
    return ctx.hooks.session_context
