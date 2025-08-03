import asyncio
from typing import Any, Awaitable, Callable

from pulse.diff import diff_vdom
from pulse.messages import (
    ServerInitMessage,
    ServerUpdateMessage,
)
from pulse.reactive import ReactiveContext, UpdateBatch
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
        self.ctx = ReactiveContext()
        self.scheduler = UpdateBatch()
        self.callback_registry: dict[str, Callable] = {}
        self.vdom: VDOMNode | None = None

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
        self.message_listeners.clear()
        self.vdom = None
        self.callback_registry.clear()
        for state, fields in self.ctx.client_states.items():
            state.remove_listener(fields, self.rerender)

    def execute_callback(self, key: str, args: list | tuple):
        with UpdateBatch():
            self.callback_registry[key](*args)

    def hydrate(self, path: str):
        route = self.routes.find(path)

        # Clear old state listeners from previous route
        for state, fields in self.ctx.client_states.items():
            state.remove_listener(fields, self.rerender)

        # Reinitialize render state for the new route
        self.current_route = path
        self.ctx = ReactiveContext.empty()
        self.callback_registry.clear()
        self.vdom = None

        with self.ctx.next_render() as new_ctx:
            node_tree = route.render_fn()
            vdom_tree, callbacks = node_tree.render()
            self.vdom = vdom_tree
            self.callback_registry = callbacks
            self.ctx = new_ctx

            # Set up new state subscriptions
            for state, fields in self.ctx.client_states.items():
                state.add_listener(fields, self.rerender)

            # Send the full VDOM to the client for initial hydration
            self.notify(ServerInitMessage(type="vdom_init", vdom=vdom_tree))

    def rerender(self):
        if self.current_route is None:
            raise RuntimeError("Failed to rerender: no route set for the session!")

        route = self.routes.find(self.current_route)

        with self.ctx.next_render() as new_ctx:
            new_node_tree = route.render_fn()
            new_vdom_tree, new_callbacks = new_node_tree.render()

            operations = diff_vdom(self.vdom, new_vdom_tree)

            # Update state listeners
            for state, fields in self.ctx.client_states.items():
                state.remove_listener(fields, self.rerender)
            for state, fields in new_ctx.client_states.items():
                state.add_listener(fields, self.rerender)

            self.callback_registry = new_callbacks
            self.vdom = new_vdom_tree
            self.ctx = new_ctx

            # Send diff to client if there are any changes
            if operations:
                self.notify(ServerUpdateMessage(type="vdom_update", ops=operations))

