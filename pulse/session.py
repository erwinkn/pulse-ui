import logging
from typing import Any, Callable
import traceback

from pulse.diff import diff_vdom
from pulse.messages import (
    RouteInfo,
    ServerInitMessage,
    ServerMessage,
    ServerUpdateMessage,
    ServerErrorMessage,
)
from pulse.reactive import Batch, ReactiveContext
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
        self._rc = ReactiveContext()

    def connect(
        self,
        message_listener: Callable[[ServerMessage], Any],
    ):
        self.message_listeners.add(message_listener)
        # Return a disconnect function. Use `discard` since there are two ways
        # of disconnecting a message listener
        return lambda: (self.message_listeners.discard(message_listener),)

    # Use `discard` since there are two ways of disconnecting a message listener
    def disconnect(self, message_listener: Callable[[ServerMessage], Any]):
        self.message_listeners.discard(message_listener)

    def notify(self, message: ServerMessage):
        for listener in self.message_listeners:
            listener(message)

    def report_error(
        self,
        path: str,
        phase: str,
        exc: Exception,
        details: dict[str, Any] | None = None,
    ):
        error_msg: ServerErrorMessage = {
            "type": "server_error",
            "path": path,
            "error": {
                "message": str(exc),
                "stack": traceback.format_exc(),
                "phase": phase,  # type: ignore
                "details": details or {},
            },
        }
        self.notify(error_msg)

    def close(self):
        # The effect will be garbage collected, and with it the dependencies
        self.message_listeners.clear()
        for path in list(self.active_routes.keys()):
            self.unmount(path)
        self.active_routes.clear()

    def execute_callback(self, route: str, key: str, args: list | tuple):
        with self._rc:
            try:
                fn, n_params = self.active_routes[route].callbacks[key]
                with Batch():
                    fn(*args[:n_params])
            except Exception as e:  # noqa: BLE001 - forward all
                self.report_error(route, "callback", e, {"callback": key})

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
                try:
                    operations = diff_vdom(res.current_vdom, res.new_vdom)
                except Exception as e:
                    self.report_error(path, "render", e)
                    return
                if operations:
                    self.notify(
                        ServerUpdateMessage(
                            type="vdom_update", path=path, ops=operations
                        )
                    )

        def on_error(e: Exception):
            self.report_error(path, 'render', e)

        with self._rc:
            print(f"Mounting '{path}'")
            route = self.routes.find(path)
            ctx = RenderContext(
                route, position="", route_info=route_info, vdom=current_vdom
            )
            self.active_routes[path] = ctx
            ctx.mount(
                on_render=on_render, on_error=on_error
            )

    def navigate(self, path: str, route_info: RouteInfo):
        # Route is already mounted, we can just update the routing state
        with self._rc:
            try:
                if path not in self.active_routes:
                    logger.error(f"Navigating to unmounted route '{path}'")
                else:
                    self.active_routes[path].update_route_info(route_info)
            except Exception as e:  # noqa: BLE001
                self.report_error(path, "navigate", e)

    def unmount(self, path: str):
        with self._rc:
            if path not in self.active_routes:
                return
            print(f"Unmounting '{path}'")
            try:
                ctx = self.active_routes.pop(path)
                ctx.unmount()
            except Exception as e:  # noqa: BLE001
                self.report_error(path, "unmount", e)
