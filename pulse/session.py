from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pulse.diff import VDOM, diff_vdom
from pulse.hooks import ReactiveState
from pulse.messages import (
    ServerInitMessage,
    ServerMessage,
    ServerUpdateMessage,
)
from pulse.reactive import Effect, batch
from pulse.routing import RouteTree
from pulse.vdom import VDOMNode, Node


@dataclass
class ActiveRoute:
    callback_registry: dict[str, Callable]
    reactive_state: ReactiveState
    vdom: VDOM | None
    effect: Effect | None


class Session:
    def __init__(self, id: str, routes: RouteTree) -> None:
        self.id = id
        self.routes = routes
        self.message_listeners: set[Callable[[ServerMessage], Any]] = set()

        self.active_routes: dict[str, ActiveRoute] = {}
        self.vdom: VDOMNode | None = None

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
            self.leave(path)
        self.active_routes.clear()

    def execute_callback(self, route: str, key: str, args: list | tuple):
        with batch():
            self.active_routes[route].callback_registry[key](*args)

    def navigate(self, path: str):
        if path in self.active_routes:
            raise RuntimeError(f"Cannot navigate to already active route '{path}'")

        route = self.routes.find(path)
        active_route = ActiveRoute(
            callback_registry={},
            reactive_state=ReactiveState.create(),
            vdom=None,
            effect=None,
        )

        def render():
            with active_route.reactive_state.start_render() as new_reactive_state:
                # The render_fn is expected to return a single VDOMNode
                previous_vdom = active_route.vdom
                new_node = route.render.fn() # type: ignore
                new_vdom, new_callbacks = new_node.render()

                active_route.reactive_state = new_reactive_state
                active_route.callback_registry = new_callbacks
                active_route.vdom = new_vdom
                if new_reactive_state.render_count == 1:
                    self.notify(
                        ServerInitMessage(type="vdom_init", path=path, vdom=new_vdom)
                    )
                else:
                    operations = diff_vdom(previous_vdom, new_vdom)
                    if operations:
                        self.notify(
                            ServerUpdateMessage(
                                type="vdom_update", path=path, ops=operations
                            )
                        )

        active_route.effect = Effect(render)
        self.active_routes[path] = active_route

    def leave(self, path: str):
        active_route = self.active_routes.pop(path)
        if active_route.effect:
            active_route.effect.dispose()
