"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import logging
import os
import socket
from enum import IntEnum
from typing import Any, Callable, List, Optional, TypeVar

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pulse.codegen import CodegenConfig
from pulse.diff import diff_vdom
from pulse.messages import (
    ClientMessage,
    ServerInitMessage,
    ServerUpdateMessage,
)
from pulse.reactive import ReactiveContext, UpdateScheduler
from pulse.vdom import Node, ReactComponent

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Route:
    """
    Represents a route definition with its component dependencies.
    """

    def __init__(
        self,
        path: str,
        render_fn: Callable[[], Node],
        components: list[ReactComponent],
    ):
        self.path = path
        self.render_fn = render_fn
        self.components = components


def route(
    path: str, components: list[ReactComponent] | None = None
) -> Callable[[Callable[[], Node]], Route]:
    """
    Decorator to define a route with its component dependencies.

    Args:
        path: URL path for the route
        components: List of component keys used by this route

    Returns:
        Decorator function
    """

    def decorator(render_func: Callable[[], Node]) -> Route:
        route = Route(path, render_func, components=components or [])
        add_route(route)
        return route

    return decorator


# Global registry for routes
ROUTES: list[Route] = []


def add_route(route: Route):
    """Register a route in the global registry"""
    ROUTES.append(route)


def decorated_routes() -> list[Route]:
    """Get all registered routes"""
    return ROUTES.copy()


def clear_routes():
    """Clear all registered routes"""
    global ROUTES
    ROUTES = []


class AppStatus(IntEnum):
    created = 0
    initialized = 1
    running = 2
    stopped = 3


class App:
    """
    Pulse UI Application - the main entry point for defining your app.

    Similar to FastAPI, users create an App instance and define their routes.

    Example:
        ```python
        import pulse as ps

        app = ps.App()

        @app.route("/")
        def home():
            return ps.div("Hello World!")
        ```
    """

    def __init__(
        self,
        routes: Optional[List[Route]] = None,
        codegen: Optional[CodegenConfig] = None,
    ):
        """
        Initialize a new Pulse App.

        Args:
            routes: Optional list of Route objects to register.
            codegen: Optional codegen configuration.
        """
        routes = routes or []
        self.routes: dict[str, Route] = {}
        for route_obj in routes:
            if route_obj.path in self.routes:
                raise ValueError(f"Duplicate routes on path '{route_obj.path}'")
            self.routes[route_obj.path] = route_obj
        self.sessions: dict[str, Session] = {}

        self.codegen = codegen or CodegenConfig()

        self.fastapi = FastAPI(title="Pulse UI Server")
        self.sio = socketio.AsyncServer(async_mode="asgi")
        self.asgi = socketio.ASGIApp(self.sio, self.fastapi)
        self.status = AppStatus.created

    def setup(self):
        if self.status >= AppStatus.initialized:
            logger.warn("Called App.setup() on an already initialized application")
            return

        # Add CORS middleware
        self.fastapi.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @self.fastapi.get("/health")
        def healthcheck():
            return {"health": "ok", "message": "Pulse server is running"}

    def run(self, host: str = "127.0.0.1", port=8000, find_port=True):
        if self.status == AppStatus.running:
            raise RuntimeError("Server already running")
        if self.status == AppStatus.created:
            self.setup()

        self.setup()
        if find_port:
            port = find_available_port(port)

        logger.info(f"🚀 Starting Pulse UI Server on http://{host}:{port}")
        logger.info(f"🔌 WebSocket endpoint: ws://{host}:{port}/ws")

        uvicorn.run(self.asgi, host=host, port=port, log_level="info")

    def _setup_socketio_endpoints(self):
        @self.sio.event
        def connect(sid: str, data):
            session = self.create_session(sid)
            session.connect(
                lambda message: self.sio.emit("message", message, to=sid),
            )

        @self.sio.event
        def disconnect(sid: str, data):
            # TODO: keep the session open for some time in case the client reconnects?
            self.close_session(sid)

        @self.sio.event
        def message(sid: str, data: ClientMessage):
            session = self.get_session(sid)

            if data["type"] == "navigate":
                session.hydrate(data["route"])
            elif data["type"] == "callback":
                session.execute_callback(data["callback"], data["args"])
            else:
                logger.warning(f"Unknown message type received: {data}")

    def route(self, path: str, components: Optional[List] = None):
        """
        Decorator to define a route on this app instance.

        Args:
            path: URL path for the route
            components: List of component keys used by this route

        Returns:
            Decorator function
        """

        def decorator(render_func):
            route_obj = Route(path, render_func, components=components or [])
            self.add_route(route_obj)
            return route_obj

        return decorator

    def add_route(self, route: Route):
        """Add a route to this app instance."""
        if route.path in self.routes:
            raise ValueError(f"Duplicate routes on path '{route.path}'")
        self.routes[route.path] = route

    def list_routes(self) -> List[Route]:
        """Get all routes registered on this app (both via constructor and decorator)."""
        return list(self.routes.values())

    def clear_routes(self):
        """Clear all routes from this app instance."""
        self.routes.clear()

    def get_route(self, path: str):
        if path not in self.routes:
            raise ValueError(f"No route found for path '{path}'")
        return self.routes[path]

    def create_session(self, id: str):
        if id in self.sessions:
            raise ValueError(f"Session {id} already exists")
        self.sessions[id] = Session(id, self)
        return self.sessions[id]

    def get_session(self, id: str):
        if id not in self.sessions:
            raise KeyError(f"Session {id} does not exist")
        return self.sessions[id]

    def close_session(self, id: str):
        if id not in self.sessions:
            raise KeyError(f"Session {id} does not exist")
        self.sessions[id].close()
        del self.sessions[id]


class Session:
    def __init__(self, id: str, app: App) -> None:
        self.id = id
        self.app = app
        self.message_listeners: set[
            Callable[[ServerUpdateMessage | ServerInitMessage], Any]
        ] = set()

        self.current_route: str | None = None
        self.ctx = ReactiveContext()
        self.scheduler = UpdateScheduler()
        self.callback_registry: dict[str, Callable] = {}
        self.vdom: Node | None = None

    def connect(
        self,
        message_listener: Callable[[ServerUpdateMessage | ServerInitMessage], Any],
    ):
        self.message_listeners.add(message_listener)
        # Return a disconnect function
        return lambda: (self.message_listeners.remove(message_listener),)

    def notify(self, message: ServerUpdateMessage | ServerInitMessage):
        for listener in self.message_listeners:
            listener(message)

    def close(self):
        self.message_listeners.clear()
        self.vdom = None
        self.callback_registry.clear()
        for state, fields in self.ctx.client_states.items():
            state.remove_listener(fields, self.rerender)

    def execute_callback(self, key: str, args: list | tuple):
        self.callback_registry[key](*args)

    def rerender(self):
        if self.current_route is None:
            raise RuntimeError("Failed to rerender: no route set for the session!")
        self.update_render()

    def hydrate(self, path: str):
        route = self.app.get_route(path)

        # Clear old state listeners from previous route
        for state, fields in self.ctx.client_states.items():
            state.remove_listener(fields, self.rerender)

        # Reinitialize render state for the new route
        self.current_route = path
        self.ctx = ReactiveContext.empty()
        self.callback_registry.clear()
        self.vdom = None

        with self.ctx.next_render() as new_ctx:
            # Render the component tree
            node_tree = route.render_fn()

            # Convert to VDOM and collect callbacks
            vdom_tree, callbacks = node_tree.render()

            # Store the state
            self.vdom = node_tree
            self.callback_registry = callbacks
            self.ctx = new_ctx

            # Set up new state subscriptions
            for state, fields in self.ctx.client_states.items():
                state.add_listener(fields, self.rerender)

            # Send the full VDOM to the client for initial hydration
            self.notify(ServerInitMessage(type="vdom_init", vdom=vdom_tree))

    def update_render(self):
        if self.current_route is None:
            return  # Should not happen if called from rerender

        route = self.app.get_route(self.current_route)

        with self.ctx.next_render() as new_ctx:
            # Render new tree
            new_node_tree = route.render_fn()

            # Diff with the old tree
            diff = diff_vdom(self.vdom, new_node_tree)

            # Unsubscribe old state listeners
            for state, fields in self.ctx.client_states.items():
                state.remove_listener(fields, self.rerender)

            # Subscribe new state listeners
            for state, fields in new_ctx.client_states.items():
                state.add_listener(fields, self.rerender)

            # Update callbacks
            remove_callbacks = self.callback_registry.keys() - diff.callbacks.keys()
            add_callbacks = diff.callbacks.keys() - self.callback_registry.keys()
            for key in remove_callbacks:
                del self.callback_registry[key]
            for key in add_callbacks:
                self.callback_registry[key] = diff.callbacks[key]

            # Update stored state
            self.vdom = new_node_tree
            self.ctx = new_ctx

            # Send diff to client if there are any changes
            if diff.operations:
                self.notify(
                    ServerUpdateMessage(type="vdom_update", ops=diff.operations)
                )


def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"Could not find available port after {max_attempts} attempts starting from {start_port}"
    )
