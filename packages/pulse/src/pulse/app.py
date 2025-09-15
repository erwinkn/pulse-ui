"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import Literal, Optional, Sequence, TypeVar, cast

import socketio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import pulse.flatted as flatted
from pulse.codegen import Codegen, CodegenConfig
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.cookies import Cookie, session_cookie
from pulse.helpers import (
    ensure_web_lock,
    get_client_address,
    get_client_address_socketio,
    later,
    lock_path_for_web_root,
    remove_web_lock,
)
from pulse.messages import ClientMessage, ServerMessage
from pulse.middleware import (
    Deny,
    MiddlewareStack,
    NotFound,
    Ok,
    PulseCoreMiddleware,
    PulseMiddleware,
    Redirect,
)
from pulse.plugin import Plugin
from pulse.react_component import ReactComponent, registered_react_components
from pulse.render_session import RenderSession
from pulse.request import PulseRequest
from pulse.routing import Layout, Route, RouteInfo, RouteTree
from pulse.hooks import RedirectInterrupt, NotFoundInterrupt
from pulse.user_session import (
    CookieSessionStore,
    SessionStore,
    UserSession,
    new_sid,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AppStatus(IntEnum):
    created = 0
    initialized = 1
    running = 2
    stopped = 3


PulseMode = Literal["dev", "ci", "prod"]


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
        dev_routes: Optional[Sequence[Route | Layout]] = None,
        codegen: Optional[CodegenConfig] = None,
        middleware: Optional[PulseMiddleware | Sequence[PulseMiddleware]] = None,
        plugins: Optional[Sequence[Plugin]] = None,
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
        # Resolve mode from environment and expose on the app instance
        mode = os.environ.get("PULSE_MODE", "dev").lower()
        if mode not in {"dev", "ci", "prod"}:
            mode = "dev"
        self.mode: PulseMode = cast(PulseMode, mode)

        # Resolve and store plugins (sorted by priority, highest first)
        self.plugins: list[Plugin] = []
        if plugins:
            self.plugins = sorted(
                list(plugins), key=lambda p: getattr(p, "priority", 0), reverse=True
            )

        # Build the complete route list from constructor args and plugins
        all_routes: list[Route | Layout] = list(routes or [])
        # Add plugin routes after user-defined routes
        for plugin in self.plugins:
            all_routes.extend(plugin.routes())
            if self.mode == "dev":
                all_routes.extend(plugin.dev_routes())

        # Auto-add React components to all routes
        add_react_components(all_routes, registered_react_components())
        self.routes = RouteTree(all_routes)
        # Default not-found path for client-side navigation on not_found()
        # Users can override via App(..., not_found_path="/my-404") in future
        setattr(self.routes, "not_found_path", "/404")
        self.user_sessions: dict[str, UserSession] = {}
        self.render_sessions: dict[str, RenderSession] = {}
        self.user_to_render: dict[str, list[str]] = defaultdict(list)
        self.render_to_user: dict[str, str] = {}

        self.codegen = Codegen(
            self.routes,
            config=codegen or CodegenConfig(),
        )

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            try:
                if isinstance(self.session_store, SessionStore):
                    await self.session_store.init()
            except Exception:
                logger.exception("Error during SessionStore.init()")
            # Create a lock file in the web project (unless the CLI manages it)
            lock_path = None
            try:
                if os.environ.get("PULSE_LOCK_MANAGED_BY_CLI") != "1":
                    try:
                        lock_path = lock_path_for_web_root(self.codegen.cfg.web_root)
                        ensure_web_lock(lock_path, owner="server")
                    except RuntimeError as e:
                        logger.error(str(e))
                        raise
            except Exception:
                logger.exception("Failed to create Pulse dev lock file")
                raise
            # Call plugin on_startup hooks before serving
            for plugin in self.plugins:
                plugin.on_startup(self)
            try:
                yield
            finally:
                try:
                    if isinstance(self.session_store, SessionStore):
                        await self.session_store.close()
                except Exception:
                    logger.exception("Error during SessionStore.close()")
                # Remove lock if we created it
                try:
                    if os.environ.get("PULSE_LOCK_MANAGED_BY_CLI") != "1" and lock_path:
                        remove_web_lock(lock_path)
                except Exception:
                    # Best-effort
                    pass

        self.fastapi = FastAPI(title="Pulse UI Server", lifespan=lifespan)
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.asgi = socketio.ASGIApp(self.sio, self.fastapi)
        if middleware is None:
            mw_stack: list[PulseMiddleware] = [PulseCoreMiddleware()]
        elif isinstance(middleware, PulseMiddleware):
            mw_stack = [PulseCoreMiddleware(), middleware]
        else:
            mw_stack = [PulseCoreMiddleware(), *middleware]

        # Let plugins contribute middleware (in plugin priority order)
        for plugin in self.plugins:
            mw_stack.extend(plugin.middleware())

        self.middleware = MiddlewareStack(mw_stack)
        self.cookie = cookie or session_cookie()
        self.session_store = session_store or CookieSessionStore()
        self._sessions_in_request: dict[str, int] = {}

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
            session = await self.get_or_create_session(cookie)
            self._sessions_in_request[session.sid] = (
                self._sessions_in_request.get(session.sid, 0) + 1
            )
            header_sid = request.headers.get("x-pulse-render-id")
            if header_sid:
                render = self.render_sessions.get(header_sid)
            else:
                render = None
            with PulseContext.update(session=session, render=render):
                res: Response = await call_next(request)
            session.handle_response(res)

            self._sessions_in_request[session.sid] -= 1
            if self._sessions_in_request[session.sid] == 0:
                del self._sessions_in_request[session.sid]

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
            client_addr: str | None = get_client_address(request)
            render = RenderSession(
                new_sid(),
                self.routes,
                server_address=self.server_address,
                client_address=client_addr,
            )

            def _prerender():
                vdom = render.render(path, route_info, prerendering=True)
                return vdom

            def _next():
                return Ok(_prerender())

            with PulseContext.update(render=render):
                try:
                    res = self.middleware.prerender(
                        path=path,
                        route_info=route_info,
                        request=PulseRequest.from_fastapi(request),
                        session=session.data,
                        next=_next,
                    )
                except RedirectInterrupt as r:
                    res = Redirect(r.path)
                except NotFoundInterrupt:
                    res = NotFound()

            self.close_render(render.id)
            if isinstance(res, Redirect):
                location = res.path or "/"
                raise HTTPException(status_code=302, headers={"Location": location})
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

        # Call on_setup hooks after FastAPI routes/middleware are in place
        for plugin in self.plugins:
            plugin.on_setup(self)

        @self.sio.event
        async def connect(sid: str, environ: dict, auth=None):
            # We use `sid` to designate UserSession ID internally
            wsid = sid
            # Determine client address/origin prior to creating the session
            client_addr: str | None = get_client_address_socketio(environ)
            # Parse cookies from environ
            cookie = self.cookie.get_from_socketio(environ)
            if cookie is None:
                raise ConnectionRefusedError()
            session = await self.get_or_create_session(cookie)
            render = self.create_render(wsid, session, client_address=client_addr)
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
                payload = flatted.stringify(message)
                try:
                    asyncio.create_task(self.sio.emit("message", payload, to=sid))
                except RuntimeError:
                    from anyio import from_thread

                    async def _emit():
                        await self.sio.emit("message", payload, to=sid)

                    from_thread.run(_emit)

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

    async def get_or_create_session(self, raw_cookie: Optional[str]) -> UserSession:
        if isinstance(self.session_store, CookieSessionStore):
            if raw_cookie is not None:
                session_data = self.session_store.decode(raw_cookie)
                if session_data:
                    sid, data = session_data
                    existing = self.user_sessions.get(sid)
                    if existing is not None:
                        return existing
                # Invalid cookie = treat as no cookie

            # No cookie: create fresh session
            sid = new_sid()
            session = UserSession(sid, {}, app=self)
            session._refresh_session_cookie(self)
            self.user_sessions[sid] = session
            return session

        if raw_cookie is not None and raw_cookie in self.user_sessions:
            return self.user_sessions[raw_cookie]

        # Server-backed store path
        assert isinstance(self.session_store, SessionStore)
        if raw_cookie is not None:
            sid = raw_cookie
            data = await self.session_store.get(sid) or await self.session_store.create(
                sid
            )
            session = UserSession(sid, data, app=self)
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
            session = UserSession(
                sid,
                data,
                app=self,
            )
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

        # If the session is currently inside an HTTP request, we don't need to schedule
        # set-cookies via WS; cookies will be attached on the HTTP response.
        if sid in self._sessions_in_request:
            return

        sess._scheduled_cookie_refresh = True
        render = self.render_sessions[render_ids[0]]
        # We don't want to wait for this to resolve
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(render.call_api("/set-cookies", method="GET"))
        except RuntimeError:
            from anyio import from_thread

            async def _schedule():
                await render.call_api("/set-cookies", method="GET")

            from_thread.run(_schedule)


def add_react_components(
    routes: Sequence[Route | Layout], components: list[ReactComponent]
):
    for route in routes:
        if route.components is None:
            route.components = components
        if route.children:
            add_react_components(route.children, components)
