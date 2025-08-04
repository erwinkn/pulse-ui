import asyncio
from typing import Any, Awaitable, Callable

from pulse.diff import diff_vdom
from pulse.messages import (
    ServerInitMessage,
    ServerUpdateMessage,
)
from pulse.reactive import Effect, batch
from pulse.routing import RouteTree
from pulse.vdom import VDOMNode


class Session:
    def __init__(self, id: str, routes: RouteTree) -> None:
        self.id = id
        self.routes = routes
        self.message_listeners: set[
            Callable[[ServerUpdateMessage | ServerInitMessage], Awaitable[Any]]
        ] = set()

        self.current_route: str | None = None
        self.callback_registry: dict[str, Callable] = {}
        self.vdom: VDOMNode | None = None
        self._effect = None

    def connect(
        self,
        message_listener: Callable[
            [ServerUpdateMessage | ServerInitMessage], Awaitable[Any]
        ],
    ):
        self.message_listeners.add(message_listener)
        # Return a disconnect function
        return lambda: (self.message_listeners.remove(message_listener),)

    async def _notify(self, message: ServerUpdateMessage | ServerInitMessage):
        await asyncio.gather(
            *(listener(message) for listener in self.message_listeners)
        )

    def notify(self, message: ServerUpdateMessage | ServerInitMessage):
        asyncio.create_task(self._notify(message))

    def close(self):
        # The effect will be garbage collected, and with it the dependencies
        self.message_listeners.clear()
        self.vdom = None
        self.callback_registry.clear()

    def execute_callback(self, key: str, args: list | tuple):
        batch(lambda: self.callback_registry[key](*args))

    def hydrate(self, path: str):
        self.current_route = path
        self.callback_registry.clear()
        self.vdom = None

        route = self.routes.find(path)

        # Initial render
        node_tree = route.render_fn()
        vdom_tree, callbacks = node_tree.render()
        self.vdom = vdom_tree
        self.callback_registry = callbacks

        # Send the full VDOM to the client for initial hydration
        self.notify(ServerInitMessage(type="vdom_init", vdom=vdom_tree))

        # Create the effect that will handle re-renders
        self._effect = create_effect(self.rerender)

    def rerender(self):
        if self.current_route is None:
            raise RuntimeError("Failed to rerender: no route set for the session!")

        route = self.routes.find(self.current_route)

        new_node_tree = route.render_fn()
        new_vdom_tree, new_callbacks = new_node_tree.render()

        if self.vdom:
            operations = diff_vdom(self.vdom, new_vdom_tree)
        else:
            operations = []  # Should not happen if hydrate is called first

        self.callback_registry = new_callbacks
        self.vdom = new_vdom_tree

        # Send diff to client if there are any changes
        if operations:
            self.notify(ServerUpdateMessage(type="vdom_update", ops=operations))
