from contextvars import ContextVar
from typing import (
    Any,
    Callable,
    Mapping,
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
from pulse.vdom import Callbacks, Node, NodeTree


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
    session_context: Mapping[str, Any]

    def __init__(
        self,
        route_info: RouteInfo,
        session_context: Mapping[str, Any] | None = None,
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
    current_node: NodeTree
    new_node: NodeTree
    new_vdom: VDOM




class RenderContext:
    route: Route | Layout
    position: str

    render_count: int
    prerendering: bool

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
        session_context: Mapping[str, Any] | None = None,
    ):
        self.route = route
        self.position = position
        self.prerendering = prerendering
        # If a current VDOM was provided (hydration), store only its Node form
        # We keep a Node reference as the authoritative server tree
        self.node: NodeTree = Node.from_vdom(vdom)

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
            current_node = self.node
            new_node = self.route.render.fn()  # type: ignore
            new_vdom, new_callbacks = new_node.render()
            if self.prerendering:
                REACTIVE_CONTEXT.get().batch.effects = []

            self.node = new_node
            self.callbacks = new_callbacks
            return RenderResult(
                render_count=self.render_count,
                current_node=current_node,
                new_node=new_node,
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

