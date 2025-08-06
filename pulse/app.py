"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
from enum import IntEnum
from typing import Optional, Sequence, TypeVar, TypedDict, Unpack

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os
from pulse.codegen import Codegen, CodegenConfig
from pulse.components.registry import ReactComponent, registered_react_components
from pulse.messages import ClientMessage, RouteInfo
from pulse.render import RenderContext
from pulse.routing import Layout, Route, RouteTree
from pulse.session import Session
from pulse.vdom import VDOM

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AppStatus(IntEnum):
    created = 0
    initialized = 1
    running = 2
    stopped = 3


class AppConfig(TypedDict, total=False):
    server_address: str


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
        routes: Optional[Sequence[Route | Layout]] = None,
        codegen: Optional[CodegenConfig] = None,
        **config: Unpack[AppConfig],
    ):
        """
        Initialize a new Pulse App.

        Args:
            routes: Optional list of Route objects to register.
            codegen: Optional codegen configuration.
        """
        self.config = config

        routes = routes or []
        # Auto-add React components to all routes
        add_react_components(routes, registered_react_components())
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

        # RouteInfo is the request body
        @self.fastapi.post("/prerender/{path:path}")
        def prerender(path: str, route_info: RouteInfo) -> VDOM:
            ctx = RenderContext(
                self.routes.find(path), route_info, prerendering=True, vdom=None
            )
            result = ctx.render()
            return result.new_vdom

        @self.sio.event
        async def connect(sid: str, environ, auth=None):
            session = self.create_session(sid)
            session.connect(
                lambda message: asyncio.create_task(
                    self.sio.emit("message", message, to=sid)
                ),
            )

        @self.sio.event
        def disconnect(sid: str):
            # TODO: keep the session open for some time in case the client reconnects?
            self.close_session(sid)

        @self.sio.event
        def message(sid: str, data: ClientMessage):
            session = self.get_session(sid)
            if data["type"] == "mount":
                session.mount(data["path"], data["routeInfo"], data["currentVDOM"])
            if data["type"] == "navigate":
                session.navigate(data["path"], data["routeInfo"])
            elif data["type"] == "callback":
                session.execute_callback(data["path"], data["callback"], data["args"])
            elif data["type"] == "leave":
                session.unmount(data["path"])
            else:
                logger.warning(f"Unknown message type received: {data}")

    def run_codegen(self, address: Optional[str] = None):
        address = address or self.config.get('server_address')
        if not address:
            raise RuntimeError("Please provide a server address to the App constructor or the Pulse CLI.")
        self.codegen.generate_all(address)

    def asgi_factory(self):
        """
        ASGI factory for uvicorn. This is called on every reload.
        """

        host = os.environ.get("PULSE_HOST", "127.0.0.1")
        port = int(os.environ.get("PULSE_PORT", 8000))
        protocol = "http" if host in ("127.0.0.1", "localhost") else "https"

        self.run_codegen(f"{protocol}://{host}:{port}")
        self.setup()
        return self.asgi

    def get_route(self, path: str):
        self.routes.find(path)

    def create_session(self, id: str):
        if id in self.sessions:
            raise ValueError(f"Session {id} already exists")
        print(f"--> Creating session {id}")
        self.sessions[id] = Session(id, self.routes)
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


def add_react_components(
    routes: Sequence[Route | Layout], components: list[ReactComponent]
):
    for route in routes:
        if route.components is None:
            route.components = components
        if route.children:
            add_react_components(route.children, components)
