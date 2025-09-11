"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
import os
import secrets
from enum import IntEnum
from typing import Optional, Sequence, TypeVar, cast
from urllib.parse import urlsplit
from uuid import uuid4

from pulse.cookies import Cookie
import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import pulse.flatted as flatted
from pulse.codegen import Codegen, CodegenConfig
from pulse.context import PulseContext
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
from pulse.reactive import Effect
from pulse.session import (
    CookieSessionStore,
    SessionCookie,
    SessionStore,
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
        cookie: Optional[SessionCookie] = None,
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
        self.render_sessions: dict[str, RenderSession] = {}

        self.codegen = Codegen(
            self.routes,
            config=codegen or CodegenConfig(),
        )

        self.fastapi = FastAPI(title="Pulse UI Server")
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.asgi = socketio.ASGIApp(self.sio, self.fastapi)
        self.status = AppStatus.created
        # Persist the server address for use by sessions (API calls, etc.)
        self.server_address: Optional[str] = server_address
        # Maps logical session id -> active websocket ids for that session
        self._session_to_ws_ids: dict[str, set[str]] = {}
        # Maps websocket id -> owning logical session id
        self._ws_to_session_id: dict[str, str] = {}
        # Allow single middleware or sequence; compose into a stack when needed
        if middleware is None:
            self.middleware: PulseMiddleware | None = None
        elif isinstance(middleware, PulseMiddleware):
            self.middleware = MiddlewareStack([PulseCoreMiddleware(), middleware])
        else:
            self.middleware = MiddlewareStack([PulseCoreMiddleware(), *middleware])

        self.cookie = cookie or SessionCookie()
        if session_store is not None:
            self.session_store = session_store
        else:
            # Default to cookie-backed sessions. Use provided secret or generate ephemeral for dev.
            secret = (
                os.environ.get("PULSE_SESSION_SECRET")
                or os.environ.get("SECRET_KEY")
                or ""
            )
            if not secret:
                # Ephemeral secret for development; cookies will be invalidated on restart
                secret = secrets.token_urlsafe(32)
                logger.warning(
                    "PULSE_SESSION_SECRET not set; using ephemeral secret for CookieSessionStore"
                )
            self.session_store = CookieSessionStore(secret)

        self.cookies_to_set: dict[str,]

    def setup(self):
        if self.status >= AppStatus.initialized:
            logger.warning("Called App.setup() on an already initialized application")
            return

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
            # Prefer an active RenderSession when provided by header
            render_session = None
            header_sid = request.headers.get("x-pulse-session-id")
            if header_sid:
                render_session = self.render_sessions.get(header_sid)

            cookie = self.cookie.get_from_fastapi(request)
            sid, session, _ = self.get_or_create_session(cookie)
            # Set context for the duration of the request; do not set cookie here
            with PulseContext(
                session=session, render=render_session, route=None, app=self
            ):
                # Handle request
                response = await call_next(request)
            new_cookie = self.session_store.cookie_value(sid, session)
            if new_cookie != cookie:
                self.cookie.set_on_fastapi_response(response, new_cookie)
            return response

        @self.fastapi.get("/health")
        def healthcheck():
            return {"health": "ok", "message": "Pulse server is running"}

        # ------- Internal helpers (response + ctx) -------
        def _respond_and_set_sid_cookie(
            payload: VDOM, sid_for_cookie: Optional[str], session: ReactiveDict
        ) -> JSONResponse:
            resp = JSONResponse(payload)
            # sid_for_cookie can be None if get_or_create failed, but normally not
            token = (
                self.session_store.cookie_value(sid_for_cookie, session)
                if sid_for_cookie is not None
                else self.session_store.cookie_value("", session)
            )
            self.cookie.set_on_fastapi_response(resp, token)
            return resp

        # RouteInfo is the request body
        @self.fastapi.post("/prerender/{path:path}")
        def prerender(path: str, route_info: RouteInfo, request: Request):
            # Provide a working reactive context (and not the global AppReactiveContext which errors)
            if not path.startswith("/"):
                path = "/" + path
            # Determine client address/origin prior to creating the session
            client_addr: str | None = _extract_client_address_from_fastapi(request)
            # Session cookie handling
            sid, session, created = self.get_or_create_session(
                self.cookie.get_from_fastapi(request)
            )
            render = RenderSession(
                uuid4().hex,
                self.routes,
                server_address=self.server_address,
                client_address=client_addr,
                session=session,
            )

            def _prerender() -> VDOM:
                return render.render(path, route_info, prerendering=True)

            if not self.middleware:
                payload = _prerender()
                return _respond_and_set_sid_cookie(payload, sid, session)
            try:

                def _next():
                    return Ok(_prerender())

                res = self.middleware.prerender(
                    path=path,
                    route_info=route_info,
                    request=PulseRequest.from_fastapi(request),
                    session=render.session,
                    next=_next,
                )
            except Exception:
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
                return _respond_and_set_sid_cookie(payload, sid, session)
            # Fallback to default render
            else:
                raise NotImplementedError(f"Unexpected middleware return: {res}")

        @self.sio.event
        async def connect(sid: str, environ: dict, auth=None):
            # Determine client address/origin prior to creating the session
            client_addr: str | None = _extract_client_address_from_socketio(environ)
            # Parse cookies from environ
            cookie_sid = self.cookie.get_from_socketio(environ)
            _sid, session, _created = self.get_or_create_session(cookie_sid)
            # Create session with shared context
            render = self.create_render_session(
                sid, client_address=client_addr, session=session
            )
            # Map this websocket id to the logical session id and refcount
            self._link_ws_to_session(sid, _sid)
            if self.middleware:
                try:

                    def _next():
                        return Ok(None)

                    res = self.middleware.connect(
                        request=PulseRequest.from_socketio_environ(environ, auth),
                        session=render.session,
                        next=_next,
                    )
                except Exception as exc:
                    render.report_error("/", "connect", exc)
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

            render.connect(on_message)

        @self.fastapi.post("/pulse/set-cookie")
        def set_cookie_route(request: Request):
            # Pulse context middleware has already established the session
            try:
                token = request.query_params.get("token")  # type: ignore[attr-defined]
                resp = JSONResponse({"ok": True})
                if token:
                    # If a secure cookie registration exists, set that cookie
                    sid_header = request.headers.get("x-pulse-session-id")
                    render = (
                        self.render_sessions.get(sid_header or "")
                        if sid_header
                        else None
                    )
                    entry = render.pop_cookie_to_set(token) if render else None
                    if entry:
                        name = entry.get("name")
                        value = entry.get("value")
                        opts = entry.get("options", {}) or {}
                        if hasattr(resp, "set_cookie") and name and value:
                            resp.set_cookie(key=name, value=value, **opts)
                        return resp

                # Fallback: set/update the Pulse session cookie itself
                cookie_sid = self.cookie.get_from_fastapi(request)
                sid, session, _ = self.get_or_create_session(cookie_sid)
                token_value = self.session_store.cookie_value(sid, session)
                self.cookie.set_on_fastapi_response(resp, token_value)
                return resp
            except Exception:
                logger.exception("/pulse/set-cookie failed")
                raise HTTPException(status_code=500)

        @self.sio.event
        def disconnect(sid: str):
            self.close_session(sid)

        @self.sio.event
        def message(sid: str, data: ClientMessage):
            try:
                # Deserialize the message using flatted
                data = flatted.parse(data)
                render = self.render_sessions[sid]

                def _handler(render: RenderSession) -> None:
                    # Per-message middleware guard
                    if self.middleware:
                        try:
                            # Run middleware within the session's reactive context
                            res = self.middleware.message(
                                data=data,
                                session=render.session,
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

                _handler(render)
            except Exception as e:
                try:
                    # Best effort: report error for this path if available
                    path = cast(
                        str, data.get("path", "") if isinstance(data, dict) else ""
                    )
                    maybe_render = self.render_sessions.get(sid)
                    if maybe_render:
                        maybe_render.report_error(path, "server", e)
                    else:
                        logger.exception("Error handling client message: %s", data)
                except Exception as e:
                    logger.exception("Error while reporting server error: %s", e)

    def get_or_create_session(self, sid: Optional[str]):
        created = False
        session = self.session_store.get(sid) if sid else None
        if sid is None or session is None:
            sid = new_sid()
            session = self.session_store.create(sid)
            created = True
        return sid, session, created

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
        return self.asgi

    def get_route(self, path: str):
        self.routes.find(path)

    def create_render_session(
        self, id_: str, *, client_address: Optional[str] = None, session=None
    ):
        if id_ in self.render_sessions:
            raise ValueError(f"RenderSession {id_} already exists")
        # print(f"--> Creating session {id}")
        self.render_sessions[id_] = RenderSession(
            id_,
            self.routes,
            server_address=self.server_address,
            client_address=client_address,
            session=session,
        )
        return self.render_sessions[id_]

    def close_session(self, id: str):
        if id not in self.render_sessions:
            raise KeyError(f"RenderSession {id} does not exist")
        # Refcount and dispose autosave when the last WS for this session id closes
        try:
            sess_id = self._unlink_ws_from_session(id)
            if sess_id is not None:
                self._dispose_autosave_if_inactive(sess_id)
        except Exception:
            pass
        self.render_sessions[id].close()
        del self.render_sessions[id]

    def register_user_cookie(self, sid: str, cookie: Cookie, value: str): ...

    # ----- Render<->Session mapping helpers -----
    def _link_ws_to_session(self, ws_id: str, session_id: str) -> None:
        """Associate a websocket id to a logical session id and update refcounts."""
        self._ws_to_session_id[ws_id] = session_id
        ws_set = self._session_to_ws_ids.get(session_id)
        if ws_set is None:
            ws_set = set()
            self._session_to_ws_ids[session_id] = ws_set
        ws_set.add(ws_id)

    def _unlink_ws_from_session(self, ws_id: str) -> str | None:
        """Remove a websocket id mapping. Returns the associated session id if any."""
        session_id = self._ws_to_session_id.pop(ws_id, None)
        if session_id is not None:
            ws_ids = self._session_to_ws_ids.get(session_id)
            if ws_ids and ws_id in ws_ids:
                ws_ids.discard(ws_id)
                if not ws_ids:
                    self._session_to_ws_ids.pop(session_id, None)
        return session_id

    def _get_session_id_for_ws(self, ws_id: str) -> str | None:
        return self._ws_to_session_id.get(ws_id)

    def _get_ws_ids_for_session(self, session_id: str) -> set[str] | None:
        return self._session_to_ws_ids.get(session_id)

    def _dispose_autosave_if_inactive(self, session_id: str) -> None:
        """Dispose autosave effect when no active websockets are left for the session."""
        ws_ids = self._session_to_ws_ids.get(session_id)
        if not ws_ids:
            eff = self._session_autosave_effects.pop(session_id, None)
            if eff is not None:
                try:
                    eff.dispose()
                except Exception:
                    pass

    def get_active_render_for_session(self, session_id: str) -> RenderSession | None:
        """Pick any active RenderSession associated with the given logical session id."""
        try:
            ws_ids = self._session_to_ws_ids.get(session_id)
            if not ws_ids:
                return None
            wsid = next(iter(ws_ids))
            return self.render_sessions.get(wsid)
        except Exception:
            return None


def add_react_components(
    routes: Sequence[Route | Layout], components: list[ReactComponent]
):
    for route in routes:
        if route.components is None:
            route.components = components
        if route.children:
            add_react_components(route.children, components)


def _extract_client_address_from_fastapi(request: Request) -> str | None:
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
