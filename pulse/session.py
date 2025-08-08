import logging
from typing import Any, Awaitable, Callable

from pulse.diff import diff_vdom
from pulse.messages import (
    RouteInfo,
    ServerInitMessage,
    ServerMessage,
    ServerUpdateMessage,
)
from pulse.reactive import (
    Batch,
    Epoch,
    GlobalBatch,
    ReactiveContext,
)
from pulse.render import RenderContext, RenderResult
from pulse.routing import RouteTree
from pulse.vdom import VDOM, VDOMNode

logger = logging.getLogger(__file__)


class Session:
    def __init__(self, id: str, routes: RouteTree) -> None:
        self.id = id
        self.routes = routes
        self.message_listeners: set[Callable[[ServerMessage], Any]] = set()

        self.active_routes: dict[str, RenderContext] = {}
        self.vdom: VDOMNode | None = None
        # Per-session reactive context
        self._epoch = Epoch()
        self._batch = GlobalBatch()
        self._rc = ReactiveContext(self._epoch, self._batch)

    def connect(
        self,
        message_listener: Callable[[ServerMessage], Awaitable[Any]],
    ):
        self.message_listeners.add(message_listener)
        # Return a disconnect function. Use `discard` since there are two ways
        # of disconnecting a message listener
        return lambda: (self.message_listeners.discard(message_listener),)

    # Use `discard` since there are two ways of disconnecting a message listener
    def disconnect(self, message_listener: Callable[[ServerMessage], Awaitable[Any]]):
        self.message_listeners.discard(message_listener)

    def notify(self, message: ServerMessage):
        for listener in self.message_listeners:
            listener(message)

    def close(self):
        # The effect will be garbage collected, and with it the dependencies
        self.message_listeners.clear()
        for path in list(self.active_routes.keys()):
            self.unmount(path)
        self.active_routes.clear()

    def execute_callback(self, route: str, key: str, args: list | tuple):
        with self._rc:
            fn, n_params = self.active_routes[route].callbacks[key]
            with Batch():
                fn(*args[:n_params])

    def mount(self, path: str, route_info: RouteInfo, current_vdom: VDOM):
        if path in self.active_routes:
            logger.error(f"Route already mounted: '{path}'")
            return

        def on_render(res: RenderResult):
            if res.current_vdom is None:
                self.notify(
                    ServerInitMessage(type="vdom_init", path=path, vdom=res.new_vdom)
                )
            else:
                operations = diff_vdom(res.current_vdom, res.new_vdom)
                if operations:
                    self.notify(
                        ServerUpdateMessage(
                            type="vdom_update", path=path, ops=operations
                        )
                    )

        with self._rc:
            print(f"Mounting '{path}'")
            route = self.routes.find(path)
            ctx = RenderContext(
                route, position="", route_info=route_info, vdom=current_vdom
            )
            self.active_routes[path] = ctx
            ctx.mount(on_render)

    def navigate(self, path: str, route_info: RouteInfo):
        # Route is already mounted, we can just update the routing state
        with self._rc:
            if path not in self.active_routes:
                logger.error(f"Navigating to unmounted route '{path}'")
            else:
                self.active_routes[path].update_route_info(route_info)

    def unmount(self, path: str):
        with self._rc:
            if path not in self.active_routes:
                return
            print(f"Unmounting '{path}'")
            ctx = self.active_routes.pop(path)
            ctx.unmount()
