"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
import os
from enum import IntEnum
from typing import Optional, Sequence, TypedDict, TypeVar, Unpack
from uuid import uuid4

import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from pulse.codegen import Codegen, CodegenConfig
from pulse.react_component import ReactComponent, registered_react_components
from pulse.messages import ClientMessage, RouteInfo, ServerMessage
from pulse import flatted
from pulse.middleware import (
    Deny,
    MiddlewareStack,
    NotFound,
    Ok,
    PulseMiddleware,
    Redirect,
)
from pulse.reactive import (
    REACTIVE_CONTEXT,
    Epoch,
    GlobalBatch,
    ReactiveContext,
    Scope,
)
from pulse.request import PulseRequest
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
        middleware: Optional[PulseMiddleware | Sequence[PulseMiddleware]] = None,
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
        # Allow single middleware or sequence; compose into a stack when needed
        if middleware is None:
            self._middleware: PulseMiddleware | None = None
        elif isinstance(middleware, PulseMiddleware):
            self._middleware = middleware
        else:
            self._middleware = MiddlewareStack(middleware)

    def setup(self):
        if self.status >= AppStatus.initialized:
            logger.warning("Called App.setup() on an already initialized application")
            return

        # Add CORS middleware
        REACTIVE_CONTEXT.set(AppReactiveContext())
        self.fastapi.add_middleware(
            CORSMiddleware,
            allow_origin_regex=".*",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @self.fastapi.get("/health")
        def healthcheck():
            return {"health": "ok", "message": "Pulse server is running"}

        # RouteInfo is the request body
        @self.fastapi.post("/prerender/{path:path}")
        def prerender(path: str, route_info: RouteInfo, request: Request) -> VDOM:
            # Provide a working reactive context (and not the global AppReactiveContext which errors)
            if not path.startswith("/"):
                path = "/" + path
            session = Session(uuid4().hex, self.routes)

            def _render() -> VDOM:
                return session.render(path, route_info, prerendering=True)

            if not self._middleware:
                return _render()
            try:

                def _next():
                    return Ok(_render())

                with session.reactive_context:
                    res = self._middleware.prerender(
                        path=path,
                        route_info=route_info,
                        request=PulseRequest.from_fastapi(request),
                        context=session.context,
                        next=_next,
                    )
            except Exception:
                logger.exception("Error in prerender middleware")
                res = Ok(_render())
            if isinstance(res, Redirect):
                raise HTTPException(
                    status_code=302, headers={"Location": res.path or "/"}
                )
            elif isinstance(res, NotFound):
                raise HTTPException(status_code=404)
            elif isinstance(res, Ok):
                return res.payload
            # Fallback to default render
            else:
                raise NotImplementedError(f"Unexpected middleware return: {res}")

        @self.sio.event
        async def connect(sid: str, environ, auth=None):
            # Create session first to instantiate reactive and session contexts
            session = self.create_session(sid)
            if self._middleware:
                try:

                    def _next():
                        return Ok(None)

                    # Ensure middleware executes within the session's reactive context
                    with session.reactive_context:
                        res = self._middleware.connect(
                            request=PulseRequest.from_socketio_environ(environ, auth),
                            ctx=session.context,
                            next=_next,
                        )
                except Exception:
                    logger.exception("Error in connect middleware")
                    res = Ok(None)
                if isinstance(res, Deny):
                    # Tear down the created session if denied
                    try:
                        self.close_session(sid)
                    finally:
                        return False

            def on_message(message: ServerMessage):
                message = flatted.stringify(message)
                asyncio.create_task(self.sio.emit("message", message, to=sid))

            session.connect(on_message)

        @self.sio.event
        def disconnect(sid: str):
            self.close_session(sid)

        @self.sio.event
        def message(sid: str, data: ClientMessage):
            try:
                # Deserialize the message using flatted
                data = flatted.parse(data)
                session = self.sessions[sid]

                def _handler(sess: Session) -> None:
                    # Per-message middleware guard
                    if self._middleware:
                        try:
                            # Run middleware within the session's reactive context
                            with sess.reactive_context:
                                res = self._middleware.message(
                                    ctx=sess.context,
                                    data=data,
                                    next=lambda: Ok(None),
                                )
                            if isinstance(res, Deny):
                                # Report as server error for this path
                                path = data.get("path")
                                sess.report_error(
                                    path or "api_response",
                                    "server",
                                    Exception("Request denied by server"),
                                    {"kind": "deny"},
                                )
                                return
                        except Exception:
                            logger.exception("Error in message middleware")
                    if data["type"] == "mount":
                        sess.mount(data["path"], data["routeInfo"])
                    elif data["type"] == "navigate":
                        sess.navigate(data["path"], data["routeInfo"])
                    elif data["type"] == "callback":
                        sess.execute_callback(
                            data["path"], data["callback"], data["args"]
                        )
                    elif data["type"] == "unmount":
                        sess.unmount(data["path"])
                    elif data["type"] == "api_result":
                        # type: ignore[union-attr]
                        sess.handle_api_result(data)  # type: ignore[arg-type]
                    else:
                        logger.warning(f"Unknown message type received: {data}")

                _handler(session)
            except Exception as e:
                try:
                    # Best effort: report error for this path if available
                    path = data.get("path", "") if isinstance(data, dict) else ""
                    session = self.sessions.get(sid)
                    if session:
                        session.report_error(path, "server", e)
                    else:
                        logger.exception("Error handling client message: %s", data)
                except Exception as e:
                    logger.exception("Error while reporting server error: %s", e)

    def run_codegen(self, address: Optional[str] = None):
        address = address or self.config.get("server_address")
        if not address:
            raise RuntimeError(
                "Please provide a server address to the App constructor or the Pulse CLI."
            )
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


class AppReactiveContext(ReactiveContext):
    def __init__(self, allow_usage=False) -> None:
        self._epoch = Epoch()
        self._batch = GlobalBatch()
        self._scope = Scope()
        self.allow_usage = allow_usage

    @property
    def epoch(self):
        if self.allow_usage:
            return self._epoch
        raise RuntimeError(
            "App reactive context should not be used, all reactive context should be scoped to sessions."
        )

    @property
    def batch(self):
        if self.allow_usage:
            return self._batch
        raise RuntimeError(
            "App reactive context should not be used, all reactive context should be scoped to sessions."
        )

    @property
    def scope(self):
        if self.allow_usage:
            return self._scope
        raise RuntimeError(
            "App reactive context should not be used, all reactive context should be scoped to sessions."
        )
