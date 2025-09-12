"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
from collections import defaultdict
import logging
import os
from enum import IntEnum
from typing import Optional, Sequence, TypeVar, cast
from urllib.parse import urlsplit
from uuid import uuid4

from pulse.cookies import Cookie, session_cookie
from pulse.helpers import later
import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import pulse.flatted as flatted
from pulse.codegen import Codegen, CodegenConfig
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.messages import ClientMessage, ServerMessage
from pulse.middleware import (
    Deny,
    MiddlewareStack,
    NotFound,
    Ok,
    PulseMiddleware,
    Redirect,
    PulseCoreMiddleware,
)
from pulse.react_component import ReactComponent, registered_react_components
from pulse.reactive_extensions import ReactiveDict
from pulse.render_session import RenderSession
from pulse.request import PulseRequest
from pulse.routing import Layout, Route, RouteInfo, RouteTree
from pulse.user_session import (
    CookieSessionStore,
    SessionStore,
    UserSession,
    new_sid,
)
from pulse.vdom import VDOM

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
        middleware: Optional[PulseMiddleware | Sequence[PulseMiddleware]] = None,
        cookie: Optional[Cookie] = None,
        session_store: Optional[SessionStore] = None,
        server_address: Optional[str] = None,
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
        self.user_sessions: dict[str, UserSession] = {}
        self.render_sessions: dict[str, RenderSession] = {}
        self.user_to_render: dict[str, list[str]] = defaultdict(list)
        self.render_to_user: dict[str, str] = {}

        self.codegen = Codegen(
            self.routes,
            config=codegen or CodegenConfig(),
        )

        self.fastapi = FastAPI(title="Pulse UI Server")
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.asgi = socketio.ASGIApp(self.sio, self.fastapi)
        if middleware is None:
            self.middleware = MiddlewareStack([PulseCoreMiddleware()])
        elif isinstance(middleware, PulseMiddleware):
            self.middleware = MiddlewareStack([PulseCoreMiddleware(), middleware])
        else:
            self.middleware = MiddlewareStack([PulseCoreMiddleware(), *middleware])
        self.cookie = cookie or session_cookie()
        self.session_store = session_store or CookieSessionStore()

        self.status = AppStatus.created
        # Persist the server address for use by sessions (API calls, etc.)
        self.server_address: Optional[str] = server_address

    def run_codegen(self, address: Optional[str] = None):
        if address:
            self.server_address = address
        if not self.server_address:
            raise RuntimeError(
                "Please provide a server address to the App constructor or the Pulse CLI."
            )
        self.codegen.generate_all(self.server_address)

    def asgi_factory(self):
        """
        ASGI factory for uvicorn. This is called on every reload.
        """

        host = os.environ.get("PULSE_HOST", "127.0.0.1")
        port = int(os.environ.get("PULSE_PORT", 8000))
        protocol = "http" if host in ("127.0.0.1", "localhost") else "https"

        self.run_codegen(f"{protocol}://{host}:{port}")
        self.setup()
        self.status = AppStatus.running
        return self.asgi

    def setup(self):
        if self.status >= AppStatus.initialized:
            logger.warning("Called App.setup() on an already initialized application")
            return

        PULSE_CONTEXT.set(PulseContext(app=self))

        # Add CORS middleware
        self.fastapi.add_middleware(
            CORSMiddleware,
            allow_origin_regex=".*",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Mount PulseContext for all FastAPI routes (no route info). Other API
        # routes / middleware should be added at the module-level, which means
        # this middleware will wrap all of them.
        @self.fastapi.middleware("http")
        async def pulse_context_middleware(request: Request, call_next):
            # Session cookie handling
            cookie = self.cookie.get_from_fastapi(request)
            session = await self.get_or_create_session(cookie, handling_request=True)
            session.handling_request()
            header_sid = request.headers.get("x-pulse-render-id")
            if header_sid:
                render = self.render_sessions.get(header_sid)
            else:
                render = None
            with PulseContext.update(session=session, render=render):
                res = await call_next(request)
            session.handle_response(res)
            return res

        @self.fastapi.get("/health")
        def healthcheck():
            return {"health": "ok", "message": "Pulse server is running"}

        @self.fastapi.get("/set-cookies")
        def set_cookies():
            return {"health": "ok", "message": "Cookies updated"}

        # RouteInfo is the request body
        @self.fastapi.post("/prerender/{path:path}")
        async def prerender(path: str, route_info: RouteInfo, request: Request):
            if not path.startswith("/"):
                path = "/" + path
            # The session is set by the FastAPI HTTP middleware above
            session = PulseContext.get().session
            if session is None:
                raise RuntimeError("Internal error: couldn't resolve user session")
            client_addr: str | None = client_address_from_req(request)

            def _prerender() -> VDOM:
                # TODO: reuse RenderSession between prerender and connect
                wsid = new_sid()
                render = self.create_render(wsid, session, client_address=client_addr)
                vdom = render.render(path, route_info, prerendering=True)
                self.close_render(wsid)
                return vdom

            if not self.middleware:
                payload = _prerender()
                resp = JSONResponse(payload)
                session.handle_response(resp)
                return resp
            try:

                def _next():
                    return Ok(_prerender())

                res = self.middleware.prerender(
                    path=path,
                    route_info=route_info,
                    request=PulseRequest.from_fastapi(request),
                    session=session.data,
                    next=_next,
                )
            except Exception:
                # TODO: add ability to report errors in prerender
                logger.exception("Error in prerender middleware")
                res = Ok(_prerender())
            if isinstance(res, Redirect):
                raise HTTPException(
                    status_code=302, headers={"Location": res.path or "/"}
                )
            elif isinstance(res, NotFound):
                raise HTTPException(status_code=404)
            elif isinstance(res, Ok):
                payload = res.payload
                resp = JSONResponse(payload)
                session.handle_response(resp)
                return resp
            # Fallback to default render
            else:
                raise NotImplementedError(f"Unexpected middleware return: {res}")

        @self.sio.event
        async def connect(sid: str, environ: dict, auth=None):
            # We use `sid` to designate UserSession ID internally
            wsid = sid
            # Determine client address/origin prior to creating the session
            client_addr: str | None = _extract_client_address_from_socketio(environ)
            # Parse cookies from environ
            cookie = self.cookie.get_from_socketio(environ)
            session = await self.get_or_create_session(cookie)
            render = self.create_render(wsid, session, client_address=client_addr)
            if self.middleware:
                with PulseContext.update(session=session, render=render):

                    def _next():
                        return Ok(None)

                    try:
                        res = self.middleware.connect(
                            request=PulseRequest.from_socketio_environ(environ, auth),
                            session=session.data,
                            next=_next,
                        )
                    except Exception as exc:
                        render.report_error("/", "connect", exc)
                        res = Ok(None)
                    if isinstance(res, Deny):
                        # Tear down the created session if denied
                        self.close_render(wsid)

            def on_message(message: ServerMessage):
                message = flatted.stringify(message)
                asyncio.create_task(self.sio.emit("message", message, to=sid))

            render.connect(on_message)

        @self.sio.event
        def disconnect(sid: str):
            self.close_render(sid)

        @self.sio.event
        def message(sid: str, data: ClientMessage):
            render = self.render_sessions[sid]
            try:
                # Deserialize the message using flatted
                data = flatted.parse(data)
                session = self.user_sessions[self.render_to_user[sid]]

                # Per-message middleware guard
                with PulseContext.update(session=session, render=render):
                    if self.middleware:
                        try:
                            # Run middleware within the session's reactive context
                            res = self.middleware.message(
                                data=data,
                                session=session.data,
                                next=lambda: Ok(None),
                            )
                            if isinstance(res, Deny):
                                # Report as server error for this path
                                path = cast(str, data.get("path", "api_response"))
                                render.report_error(
                                    path,
                                    "server",
                                    Exception("Request denied by server"),
                                    {"kind": "deny"},
                                )
                                return
                        except Exception:
                            logger.exception("Error in message middleware")
                    if data["type"] == "mount":
                        render.mount(data["path"], data["routeInfo"])
                    elif data["type"] == "navigate":
                        render.navigate(data["path"], data["routeInfo"])
                    elif data["type"] == "callback":
                        render.execute_callback(
                            data["path"], data["callback"], data["args"]
                        )
                    elif data["type"] == "unmount":
                        render.unmount(data["path"])
                    elif data["type"] == "api_result":
                        # type: ignore[union-attr]
                        render.handle_api_result(data)  # type: ignore[arg-type]
                    else:
                        logger.warning(f"Unknown message type received: {data}")

            except Exception as e:
                # Best effort: report error for this path if available
                path = cast(str, data.get("path", "") if isinstance(data, dict) else "")
                render.report_error(path, "server", e)

        self.status = AppStatus.initialized

    def get_route(self, path: str):
        return self.routes.find(path)

    async def get_or_create_session(
        self, raw_cookie: Optional[str], handling_request=False
    ) -> UserSession:
        if isinstance(self.session_store, CookieSessionStore):
            if raw_cookie is not None:
                sid, data = self.session_store.decode(raw_cookie)
                existing = self.user_sessions.get(sid)
                if existing is not None:
                    return existing
                session = UserSession(sid, data, handling_request=handling_request)
            else:
                sid = new_sid()
                session = UserSession(sid, {}, handling_request=handling_request)
                session._refresh_session_cookie(self)
            self.user_sessions[sid] = session
            return session

        if raw_cookie is not None and raw_cookie in self.user_sessions:
            return self.user_sessions[raw_cookie]

        if raw_cookie is not None:
            sid = raw_cookie
            data = await self.session_store.get(sid) or await self.session_store.create(
                sid
            )
            session = UserSession(sid, data, handling_request=handling_request)
            session.set_cookie(
                name=self.cookie.name,
                value=sid,
                domain=self.cookie.domain,
                secure=self.cookie.secure,
                samesite=self.cookie.samesite,
                max_age_seconds=self.cookie.max_age_seconds,
            )
        else:
            sid = new_sid()
            data = await self.session_store.create(sid)
            session = UserSession(sid, data, handling_request=handling_request)
            session.set_cookie(
                name=self.cookie.name,
                value=sid,
                domain=self.cookie.domain,
                secure=self.cookie.secure,
                samesite=self.cookie.samesite,
                max_age_seconds=self.cookie.max_age_seconds,
            )
        self.user_sessions[sid] = session
        return session

    def create_render(
        self, wsid: str, session: UserSession, *, client_address: Optional[str] = None
    ):
        if wsid in self.render_sessions:
            raise ValueError(f"RenderSession {wsid} already exists")
        # print(f"--> Creating session {id}")
        render = RenderSession(
            wsid,
            self.routes,
            server_address=self.server_address,
            client_address=client_address,
        )
        self.render_sessions[wsid] = render
        self.render_to_user[wsid] = session.sid
        self.user_to_render[session.sid].append(wsid)
        return render

    def close_render(self, wsid: str):
        render = self.render_sessions.pop(wsid, None)
        if not render:
            return
        sid = self.render_to_user.pop(wsid)
        session = self.user_sessions[sid]
        render.close()
        self.user_to_render[session.sid].remove(wsid)

        if len(self.user_to_render[session.sid]) == 0:
            later(10, self.close_session_if_inactive, sid)

    def close_session(self, sid: str):
        session = self.user_sessions.pop(sid, None)
        self.user_to_render.pop(sid, None)
        if session:
            session.dispose()

    def close_session_if_inactive(self, sid: str):
        if len(self.user_to_render[sid]) == 0:
            self.close_session(sid)

    def refresh_cookies(self, sid: str):
        sess = self.user_sessions.get(sid)
        render_ids = self.user_to_render[sid]
        if not sess or len(render_ids) == 0:
            return

        sess._scheduled_cookie_refresh = True
        render = self.render_sessions[render_ids[0]]
        # We don't want to wait for this to resolve
        asyncio.create_task(render.call_api("/set-cookies", method="GET"))


def add_react_components(
    routes: Sequence[Route | Layout], components: list[ReactComponent]
):
    for route in routes:
        if route.components is None:
            route.components = components
        if route.children:
            add_react_components(route.children, components)


def client_address_from_req(request: Request) -> str | None:
    """Best-effort client origin/address from an HTTP request.

    Preference order:
      1) Origin (full scheme://host:port)
      1b) Referer (full URL) when Origin missing during prerender forwarding
      2) Forwarded header (proto + for)
      3) X-Forwarded-* headers
      4) request.client host:port
    """
    try:
        origin = request.headers.get("origin")
        if origin:
            return origin
        referer = request.headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"

        fwd = request.headers.get("forwarded")
        proto = request.headers.get("x-forwarded-proto") or (
            [p.split("proto=")[-1] for p in fwd.split(";") if "proto=" in p][0]
            .strip()
            .strip('"')
            if fwd and "proto=" in fwd
            else request.url.scheme
        )
        if fwd and "for=" in fwd:
            part = [p for p in fwd.split(";") if "for=" in p]
            hostport = part[0].split("for=")[-1].strip().strip('"') if part else ""
            if hostport:
                return f"{proto}://{hostport}"

        xff = request.headers.get("x-forwarded-for")
        xfp = request.headers.get("x-forwarded-port")
        if xff:
            host = xff.split(",")[0].strip()
            if host in ("127.0.0.1", "::1"):
                host = "localhost"
            return f"{proto}://{host}:{xfp}" if xfp else f"{proto}://{host}"

        host = request.client.host if request.client else ""
        port = request.client.port if request.client else None
        if host in ("127.0.0.1", "::1"):
            host = "localhost"
        if host and port:
            return f"{proto}://{host}:{port}"
        if host:
            return f"{proto}://{host}"
        return None
    except Exception:
        return None


def _extract_client_address_from_socketio(environ: dict) -> str | None:
    """Best-effort client origin/address from a WS environ mapping.

    Preference order mirrors HTTP variant using environ keys.
    """
    try:
        origin = environ.get("HTTP_ORIGIN")
        if origin:
            return origin

        fwd = environ.get("HTTP_FORWARDED")
        proto = environ.get("HTTP_X_FORWARDED_PROTO") or (
            [p.split("proto=")[-1] for p in str(fwd).split(";") if "proto=" in p][0]
            .strip()
            .strip('"')
            if fwd and "proto=" in str(fwd)
            else environ.get("wsgi.url_scheme", "http")
        )
        if fwd and "for=" in str(fwd):
            part = [p for p in str(fwd).split(";") if "for=" in p]
            hostport = part[0].split("for=")[-1].strip().strip('"') if part else ""
            if hostport:
                return f"{proto}://{hostport}"

        xff = environ.get("HTTP_X_FORWARDED_FOR")
        xfp = environ.get("HTTP_X_FORWARDED_PORT")
        if xff:
            host = str(xff).split(",")[0].strip()
            if host in ("127.0.0.1", "::1"):
                host = "localhost"
            return f"{proto}://{host}:{xfp}" if xfp else f"{proto}://{host}"

        host = environ.get("REMOTE_ADDR", "")
        port = environ.get("REMOTE_PORT")
        if host in ("127.0.0.1", "::1"):
            host = "localhost"
        if host and port:
            return f"{proto}://{host}:{port}"
        if host:
            return f"{proto}://{host}"
        return None
    except Exception:
        return None
