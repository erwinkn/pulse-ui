"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
from enum import IntEnum
from typing import List, Optional, Sequence, TypeVar

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os
from pulse.codegen import Codegen, CodegenConfig
from pulse.components.registry import registered_react_components
from pulse.messages import ClientMessage
from pulse.routing import Layout, Route, RouteTree, add_react_components
from pulse.session import Session
from pulse.vendor.flatted import parse

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
        routes: Optional[Sequence[Route | Layout]] = None,
        codegen: Optional[CodegenConfig] = None,
    ):
        """
        Initialize a new Pulse App.

        Args:
            routes: Optional list of Route objects to register.
            codegen: Optional codegen configuration.
        """
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
            if data["type"] == "navigate":
                session.navigate(data["path"])
            elif data["type"] == "callback":
                session.execute_callback(data["path"], data["callback"], data["args"])
            elif data["type"] == "leave":
                session.leave(data["path"])
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

    def asgi_factory(self):
        """
        ASGI factory for uvicorn. This is called on every reload.
        """

        host = os.environ.get("PULSE_HOST", "127.0.0.1")
        port = int(os.environ.get("PULSE_PORT", 8000))

        self.run_codegen(host=host, port=port)
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
