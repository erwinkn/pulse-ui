from contextvars import ContextVar
from multiprocessing import Value
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
from pulse.reactive import BATCH, Effect
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

    def __init__(
        self, value: Any = None, last_access: int = 0, initialized: bool = False
    ):
        self.value = value
        self.last_access = last_access
        self.initialized = initialized


class Router(State):
    pathname: str
    hash: str
    query: str
    queryParams: dict[str, str]
    pathParams: dict[str, str]
    catchall: list[str]

    def __init__(self, info: RouteInfo):
        self.__update_route_info(info)
        super().__init__()

    def __update_route_info(self, info: RouteInfo):
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

    def __init__(self, route_info: RouteInfo):
        self.setup = SetupState()
        self.effects = ()
        self.states = ()
        self.router = Router(route_info)

    def dispose(self):
        if isinstance(self.effects, Effect):
            self.effects.dispose()
        else:
            for effect in self.effects:
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
    ):
        self.route = route
        self.position = position
        self.prerendering = prerendering
        self.vdom = vdom

        self.render_count = 0
        self.children = []

        self.callbacks = {}
        self.hooks = HookState(route_info=route_info)
        self.effect = None

    def update_route_info(self, info: RouteInfo):
        self.hooks.router.__update_route_info(info)

    def mount(self, on_render: Callable[[RenderResult], None]):
        if self.effect is not None:
            raise RuntimeError("RenderContext is already mounted")
        self.effect = Effect(lambda: on_render(self.render()), immediate=True)

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
                batch = BATCH.get()
                batch._effects = []

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
        state.value = init_func(*args, **kwargs)
        state.initialized = True
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


def states(*args):
    ctx = RENDER_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.states` can only be called within a component, during rendering."
        )

    if ctx.render_count == 1:
        states: list[State] = []
        for arg in args:
            if callable(arg):
                states.append(arg())
            else:
                states.append(arg)
        ctx.hooks.states = tuple(states)

    if len(ctx.hooks.states) == 1:
        return ctx.hooks.states[0]
    else:
        return ctx.hooks.states


def effects(*fns: Callable[[], None]) -> None:
    # Assumption: RenderContext will set up a render context and a batch before
    # rendering. The batch ensures the effects run *after* rendering.
    ctx = RENDER_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.states` can only be called within a component, during rendering."
        )

    # Remove the effects passed here from the batch, ensuring they only run on mount
    if ctx.render_count == 1:
        effects = []
        for fn in fns:
            if not callable(fn):
                raise ValueError("Only pass functions or callable objects to `ps.effects`")
            effects.append(Effect(fn, name=fn.__name__))
        ctx.hooks.effects = tuple(effects)


def router():
    ctx = RENDER_CONTEXT.get()
    if not ctx:
        raise RuntimeError(
            "`pulse.router` can only be called within a component, during rendering."
        )
    return ctx.hooks.router
