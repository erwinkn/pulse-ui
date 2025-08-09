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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import os
from pulse.codegen import Codegen, CodegenConfig
from pulse.components.registry import ReactComponent, registered_react_components
from pulse.messages import ClientMessage, RouteInfo
from pulse.reactive import (
    REACTIVE_CONTEXT,
    Epoch,
    GlobalBatch,
    ReactiveContext,
    Scope,
)
from pulse.render import RenderContext
from pulse.routing import Layout, Route, RouteTree
from pulse.session import Session
from pulse.vdom import VDOM
from pulse.middleware import (
    PulseMiddleware,
    PrerenderResponse,
    ConnectResult,
    MessageResult,
)
from fastapi import HTTPException
from pulse.request import PulseRequest

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
        middleware: Optional[PulseMiddleware] = None,
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
        self._middleware: PulseMiddleware | None = middleware

    def setup(self):
        if self.status >= AppStatus.initialized:
            logger.warning("Called App.setup() on an already initialized application")
            return

        # Add CORS middleware
        REACTIVE_CONTEXT.set(AppReactiveContext())
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
        def prerender(path: str, route_info: RouteInfo, request: Request) -> VDOM:
            # Provide a working reactive context (and not the global AppReactiveContext which errors)
            with ReactiveContext():
                # Build request context (mutable dict passed to middleware)
                req_ctx: dict[str, object] = {}
                session_ctx: dict[str, object] = {}

                def _default_render() -> VDOM:
                    ctx = RenderContext(
                        self.routes.find(path),
                        route_info,
                        prerendering=True,
                        vdom=None,
                        session_context=session_ctx,
                    )
                    result = ctx.render()
                    return result.new_vdom

                if self._middleware:
                    try:

                        def _next() -> PrerenderResponse:
                            # Seed session context with any values set in the request context
                            session_ctx.update(req_ctx)
                            return {"kind": "ok", "vdom": _default_render()}

                        res = self._middleware.prerender(
                            path=path,
                            route_info=route_info,  # type: ignore[arg-type]
                            request=PulseRequest.from_fastapi(request),
                            context=req_ctx,
                            next=_next,
                        )
                    except Exception:
                        logger.exception("Error in prerender middleware")
                        res = {"kind": "ok", "vdom": _default_render()}

                    kind = res.get("kind", "ok")
                    if kind == "redirect":
                        location = res.get("location")
                        raise HTTPException(
                            status_code=302, headers={"Location": location or "/"}
                        )
                    if kind == "unauthorized":
                        raise HTTPException(status_code=401)
                    if kind == "not_found":
                        raise HTTPException(status_code=404)
                    vdom = res.get("vdom")
                    return vdom if vdom is not None else _default_render()
                else:
                    return _default_render()

        @self.sio.event
        async def connect(sid: str, environ, auth=None):
            # Build request context via middleware for the session
            session_ctx: dict[str, object] = {}
            if self._middleware:
                try:

                    def _next() -> ConnectResult:
                        return {"kind": "ok"}

                    res = self._middleware.connect(
                        request=PulseRequest.from_socketio_environ(environ, auth),
                        ctx=session_ctx,
                        next=_next,
                    )
                except Exception:
                    logger.exception("Error in connect middleware")
                    res = {"kind": "ok", "session_context": session_ctx}
                if res.get("kind") == "unauthorized":
                    await self.sio.disconnect(sid)
                    return
                # middleware mutates session_ctx in-place

            session = self.create_session(sid)
            session.context = session_ctx  # type: ignore[assignment]
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
            try:
                session = self.get_session(sid)

                def _default_handle(sess: Session) -> None:
                    if data["type"] == "mount":
                        sess.mount(data["path"], data["routeInfo"], data["currentVDOM"])
                    elif data["type"] == "navigate":
                        sess.navigate(data["path"], data["routeInfo"])
                    elif data["type"] == "callback":
                        sess.execute_callback(
                            data["path"], data["callback"], data["args"]
                        )
                    elif data["type"] == "unmount":
                        sess.unmount(data["path"])
                    else:
                        logger.warning(f"Unknown message type received: {data}")

                if self._middleware:
                    try:

                        def _next() -> MessageResult:
                            _default_handle(session)  # type: ignore[arg-type]
                            return {"kind": "ok"}

                        res = self._middleware.message(
                            ctx=session.context,  # type: ignore[arg-type]
                            data=data,
                            next=_next,
                        )
                        if res.get("kind") == "deny":
                            return
                        # If middleware returns ok without calling next(), we consider it handled.
                    except Exception:
                        logger.exception("Error in message middleware")
                        _default_handle(session)  # type: ignore[arg-type]
                else:
                    _default_handle(session)  # type: ignore[arg-type]
            except Exception as e:
                try:
                    # Best effort: report error for this path if available
                    path = data.get("path", "") if isinstance(data, dict) else ""
                    session = self.sessions.get(sid)
                    if session and path:
                        session.report_error(path, "server", e)
                    else:
                        logger.exception("Error handling client message")
                except Exception:
                    logger.exception("Error while reporting server error")

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
