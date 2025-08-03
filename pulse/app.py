"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
import socket
from enum import IntEnum
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pulse.codegen import Codegen, CodegenConfig
from pulse.diff import diff_vdom
from pulse.messages import (
    ClientMessage,
    ServerInitMessage,
    ServerUpdateMessage,
)
from pulse.reactive import ReactiveContext, UpdateBatch
from pulse.routing import Route, RouteTree
from pulse.vdom import VDOMNode

logger = logging.getLogger(__name__)

T = TypeVar("T")


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
        self.routes = RouteTree(routes)
        self.sessions: dict[str, Session] = {}

        self.codegen = Codegen(
            self.routes,
            config=codegen or CodegenConfig(),
        )

        self.fastapi = FastAPI(title="Pulse UI Server")
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.asgi = socketio.ASGIApp(self.sio, self.fastapi)
        self.status = AppStatus.created

    def setup(self):
        if self.status >= AppStatus.initialized:
            logger.warning("Called App.setup() on an already initialized application")
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

        @self.sio.event
        async def connect(sid: str, environ, auth=None):
            logger.info(f"-> Creating session: {sid}")
            session = self.create_session(sid)
            session.connect(
                lambda message: self.sio.emit("message", message, to=sid),
            )

        @self.sio.event
        def disconnect(sid: str):
            # TODO: keep the session open for some time in case the client reconnects?
            logger.info(f"-> Disconnecting session: {sid}")
            self.close_session(sid)

        @self.sio.event
        def message(sid: str, data: ClientMessage):
            session = self.get_session(sid)
            logger.info(f"-> Received message: {data}")

            if data["type"] == "navigate":
                session.hydrate(data["route"])
            elif data["type"] == "callback":
                session.execute_callback(data["callback"], data["args"])
            else:
                logger.warning(f"Unknown message type received: {data}")

    def run_codegen(
        self,
        host: str = "127.0.0.1",
        port=8000,
    ):
        self.codegen.host = host
        self.codegen.port = port
        self.codegen.generate_all()

    def run(
        self,
        host: str = "127.0.0.1",
        port=8000,
        find_port=True,
        log_level: str = "info",
        codegen=True,
    ):
        if self.status == AppStatus.running:
            raise RuntimeError("Server already running")
        if codegen:
            self.run_codegen(host=host, port=port)
        if self.status == AppStatus.created:
            self.setup()

        logging.basicConfig(
            level=log_level.upper(),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        if find_port:
            port = find_available_port(port)

        logger.info(f"🚀 Starting Pulse UI Server on http://{host}:{port}")
        logger.info(f"🔌 WebSocket endpoint: ws://{host}:{port}/ws")

        uvicorn.run(self.asgi, host=host, port=port, log_level=log_level)

    def route(
        self,
        path: str,
        components: Optional[List] = None,
        parent: Optional[Route] = None,
    ):
        """
        Decorator to define a route on this app instance.

        Args:
            path: URL path for the route
            components: List of component keys used by this route

        Returns:
            Decorator function
        """

        def decorator(render_func):
            route_obj = Route(path, render_func, components=components, parent=parent)
            self.add_route(route_obj)
            return route_obj

        return decorator

    def add_route(self, route: Route):
        """Add a route to this app instance."""
        self.routes.add(route)

    def get_route(self, path: str):
        self.routes.find(path)

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
        route = self.app.routes.find(path)

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

        route = self.app.routes.find(self.current_route)

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
