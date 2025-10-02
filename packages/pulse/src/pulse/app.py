"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import Any, Literal, Optional, Sequence, TypeVar, cast

import socketio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from fastapi.middleware.cors import CORSMiddleware

from pulse.serializer_v3 import Serialized, serialize, deserialize
from pulse.codegen import Codegen, CodegenConfig
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.env import PulseMode, env
from pulse.cookies import (
    CORSOptions,
    Cookie,
    cors_options,
    session_cookie,
    compute_cookie_domain,
)
from pulse.helpers import (
    create_task,
    ensure_web_lock,
    get_client_address,
    get_client_address_socketio,
    later,
    lock_path_for_web_root,
    remove_web_lock,
)
from pulse.messages import (
    ClientChannelMessage,
    ClientChannelRequestMessage,
    ClientChannelResponseMessage,
    ClientMessage,
    ClientPulseMessage,
    ServerMessage,
)
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
from pulse.css import (
    registered_css_modules,
    registered_css_imports,
    CssModule,
    CssImport,
)
from pulse.render_session import RenderSession
from pulse.request import PulseRequest
from pulse.routing import Layout, Route, RouteInfo, RouteTree
from pulse.hooks import RedirectInterrupt, NotFoundInterrupt, hooks
from pulse.user_session import (
    CookieSessionStore,
    SessionStore,
    UserSession,
    new_sid,
)
from pulse.form import FormRegistry
from pulse.channel import ChannelsManager

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AppStatus(IntEnum):
    created = 0
    initialized = 1
    running = 2
    stopped = 3


DeploymentMode = Literal["dev", "same_host", "subdomains"]


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
        internal_server_address: Optional[str] = None,
        not_found="/not-found",
        # Deployment and integration options
        mode: Optional[PulseMode] = None,
        deployment: DeploymentMode = "subdomains",
        cors: Optional[CORSOptions] = None,
        fastapi: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize a new Pulse App.

        Args:
            routes: Optional list of Route objects to register.
            codegen: Optional codegen configuration.
        """
        # Resolve mode from environment and expose on the app instance
        self.mode: PulseMode = mode or env.pulse_mode
        self.deployment: DeploymentMode = "dev" if self.mode == "dev" else deployment
        self.status = AppStatus.created
        # Persist the server address for use by sessions (API calls, etc.)
        self.server_address: Optional[str] = server_address
        # Optional internal address used by server-side loader fetches
        self.internal_server_address: Optional[str] = internal_server_address

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
        add_css_modules(all_routes, registered_css_modules())
        add_css_imports(all_routes, registered_css_imports())
        self.routes = RouteTree(all_routes)
        self.not_found = not_found
        # Default not-found path for client-side navigation on not_found()
        # Users can override via App(..., not_found_path="/my-404") in future
        self.user_sessions: dict[str, UserSession] = {}
        self.render_sessions: dict[str, RenderSession] = {}
        self.session_store = session_store or CookieSessionStore()
        self.cookie = cookie or session_cookie(mode=self.deployment)
        self.cors = cors

        # Form submissions registry
        self.forms = FormRegistry(self)
        # Channel manager for Python <-> client messaging
        self.channels = ChannelsManager(self)

        self._user_to_render: dict[str, list[str]] = defaultdict(list)
        self._render_to_user: dict[str, str] = {}
        self._sessions_in_request: dict[str, int] = {}
        # Map websocket sid -> renderId for message routing
        self._socket_to_render: dict[str, str] = {}

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
                if not env.lock_managed_by_cli:
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
                    if not env.lock_managed_by_cli and lock_path:
                        remove_web_lock(lock_path)
                except Exception:
                    # Best-effort
                    pass

        self.fastapi = FastAPI(
            title="Pulse UI Server",
            lifespan=lifespan,
        )
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

    def run_codegen(
        self, address: Optional[str] = None, internal_address: Optional[str] = None
    ):
        # Allow the CLI to disable codegen in specific scenarios (e.g., prod server-only)
        if env.codegen_disabled:
            return
        if address:
            self.server_address = address
        if internal_address:
            self.internal_server_address = internal_address
        if not self.server_address:
            raise RuntimeError(
                "Please provide a server address to the App constructor or the Pulse CLI."
            )
        self.codegen.generate_all(
            self.server_address,
            self.internal_server_address or self.server_address,
        )

    def asgi_factory(self):
        """
        ASGI factory for uvicorn. This is called on every reload.
        """

        # In prod, prefer the public server address passed to App(...).
        # In dev/ci, derive from environment variables which the CLI populates
        # based on the actual bind host/port.
        if self.mode == "prod":
            if not self.server_address:
                raise RuntimeError(
                    "In prod, please provide an explicit server_address to App(...)."
                )
            server_address = self.server_address
        else:
            host = env.pulse_host  # defaults to "localhost"
            port = env.pulse_port  # defaults to 8000
            protocol = "http" if host in ("127.0.0.1", "localhost") else "https"
            server_address = f"{protocol}://{host}:{port}"

        # Use internal server address for server-side loader if provided; fallback to public
        internal_address = self.internal_server_address or server_address
        self.run_codegen(server_address, internal_address)
        self.setup(server_address)
        self.status = AppStatus.running
        return self.asgi

    def setup(self, server_address: str):
        if self.status >= AppStatus.initialized:
            logger.warning("Called App.setup() on an already initialized application")
            return

        self.server_address = server_address
        PULSE_CONTEXT.set(PulseContext(app=self))

        hooks.lock()

        # Compute cookie domain from deployment/server address if not explicitly provided
        if self.cookie.domain is None:
            self.cookie.domain = compute_cookie_domain(
                self.deployment, self.server_address
            )

        # Add CORS middleware (configurable/overridable)
        if self.cors is not None:
            self.fastapi.add_middleware(CORSMiddleware, **self.cors)
        else:
            self.fastapi.add_middleware(
                CORSMiddleware,
                **cors_options(self.deployment, self.server_address),
            )

        # Mount PulseContext for all FastAPI routes (no route info). Other API
        # routes / middleware should be added at the module-level, which means
        # this middleware will wrap all of them.
        @self.fastapi.middleware("http")
        async def pulse_context_middleware(request: Request, call_next):
            # Skip session handling for CORS preflight requests
            if request.method == "OPTIONS":
                return await call_next(request)
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
        @self.fastapi.post("/prerender")
        async def prerender(payload: dict, request: Request):
            """
            POST /prerender
            Body: { paths: string[], routeInfo: RouteInfo, ttlSeconds?: number, renderId?: string }
            Returns: { renderId: string, <path>: VDOM, ... }
            """
            session = PulseContext.get().session
            if session is None:
                raise RuntimeError("Internal error: couldn't resolve user session")
            paths = payload.get("paths") or []
            if not isinstance(paths, list) or len(paths) == 0:
                raise HTTPException(
                    status_code=400, detail="'paths' must be a non-empty list"
                )
            route_info: RouteInfo = payload.get("routeInfo")  # type: ignore
            if not isinstance(route_info, dict):
                raise HTTPException(
                    status_code=400, detail="'routeInfo' must be an object"
                )
            ttl = payload.get("ttlSeconds")
            if not isinstance(ttl, (int, float)):
                ttl = 15

            client_addr: str | None = get_client_address(request)
            # Optional reuse of existing RenderSession
            render_id = payload.get("renderId")
            if isinstance(render_id, str):
                # Validate render exists and belongs to this user session
                existing = self.render_sessions.get(render_id)
                if existing is None:
                    raise HTTPException(status_code=400, detail="Unknown renderId")
                owner = self._render_to_user.get(render_id)
                if owner != session.sid:
                    raise HTTPException(status_code=403, detail="Forbidden renderId")
                render = existing
                cleanup = False
            else:
                render_id = new_sid()
                render = self.create_render(
                    render_id, session, client_address=client_addr
                )
                cleanup = True

            result = {"renderId": render_id, "views": {}}

            def _prerender_one(path: str):
                captured = render.prerender_mount_capture(path, route_info)
                if captured["type"] == "vdom_init":
                    return Ok(captured)
                if captured["type"] == "navigate_to":
                    nav_path = captured["path"]
                    replace = captured["replace"]
                    # Treat navigate to not_found (replace) as NotFound
                    if replace and nav_path == self.not_found:
                        return NotFound()
                    return Redirect(path=str(nav_path) if nav_path else "/")
                # Fallback: shouldn't happen, return not found to be safe
                return NotFound()

            with PulseContext.update(render=render):
                for p in paths:
                    try:
                        res = self.middleware.prerender(
                            path=p,
                            route_info=route_info,
                            request=PulseRequest.from_fastapi(request),
                            session=session.data,
                            next=lambda p=p: _prerender_one(p),
                        )
                        if isinstance(res, Ok):
                            result["views"][p] = res.payload
                        elif isinstance(res, Redirect):
                            # Abort immediately with JSON redirect signal
                            location = res.path or "/"
                            resp = JSONResponse({"redirect": location})
                            session.handle_response(resp)
                            return resp
                        elif isinstance(res, NotFound):
                            # Abort immediately with JSON notFound signal
                            resp = JSONResponse({"notFound": True})
                            session.handle_response(resp)
                            return resp
                        else:
                            raise ValueError("Unexpected prerender response:", res)
                    except RedirectInterrupt as r:
                        resp = JSONResponse({"redirect": r.path})
                        session.handle_response(resp)
                        return resp
                    except NotFoundInterrupt:
                        resp = JSONResponse({"notFound": True})
                        session.handle_response(resp)
                        return resp

                # schedule TTL cleanup if never connected
                def _gc_if_unadopted(rid: str):
                    r = self.render_sessions.get(rid)
                    if r is None:
                        return
                    if r.connected:
                        return
                    self.close_render(rid)

                if cleanup:
                    later(float(ttl), _gc_if_unadopted, render_id)

            resp = JSONResponse(result)
            session.handle_response(resp)
            return resp

        @self.fastapi.post("/pulse/forms/{form_id}")
        async def handle_form_submit(form_id: str, request: Request) -> Response:
            session = PulseContext.get().session
            if session is None:
                raise RuntimeError("Internal error: couldn't resolve user session")

            return await self.forms.handle_submit(form_id, request, session)

        # Call on_setup hooks after FastAPI routes/middleware are in place
        for plugin in self.plugins:
            plugin.on_setup(self)

        @self.sio.event
        async def connect(sid: str, environ: dict, auth: dict | None):
            # Expect renderId during websocket auth and require a valid user session
            rid = auth.get("renderId") if auth else None

            # Parse cookies from environ and ensure a session exists
            cookie = self.cookie.get_from_socketio(environ)
            if cookie is None:
                raise ConnectionRefusedError()
            session = await self.get_or_create_session(cookie)

            if not rid:
                # Still refuse connections without a renderId
                raise ConnectionRefusedError()

            # Allow reconnects where the provided renderId no longer exists by creating a new RenderSession
            render = self.render_sessions.get(rid)
            if render is None:
                render = self.create_render(
                    rid, session, client_address=get_client_address_socketio(environ)
                )
            else:
                owner = self._render_to_user.get(render.id)
                if owner != session.sid:
                    raise ConnectionRefusedError()

            def on_message(message: ServerMessage):
                payload = serialize(message)
                # `serialize` returns a tuple, which socket.io will mistake for multiple arguments
                payload = list(payload)
                create_task(self.sio.emit("message", list(payload), to=sid))

            render.connect(on_message)
            # Map socket sid to renderId for message routing
            self._socket_to_render[sid] = rid

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
                    self.close_render(rid)

        @self.sio.event
        def disconnect(sid: str):
            rid = self._socket_to_render.pop(sid, None)
            if rid is not None:
                # Close the RenderSession entirely to avoid lingering effects/tasks
                self.close_render(rid)

        @self.sio.event
        def message(sid: str, data: Serialized):
            rid = self._socket_to_render.get(sid)
            if not rid:
                return
            render = self.render_sessions.get(rid)
            if render is None:
                return
            # Use renderId mapping to user session
            session = self.user_sessions[self._render_to_user[rid]]
            # Deserialize the message using v2
            msg: ClientMessage = deserialize(data)
            try:
                if msg["type"] == "channel_message":
                    self._handle_channel_message(render, session, msg)
                else:
                    self._handle_pulse_message(render, session, msg)
            except Exception as e:
                path = cast(str, msg.get("path", "")) if isinstance(msg, dict) else ""
                render.report_error(path, "server", e)

        self.status = AppStatus.initialized

    def _handle_pulse_message(
        self, render: RenderSession, session: UserSession, msg: ClientPulseMessage
    ) -> None:
        def _next() -> Ok[None]:
            if msg["type"] == "mount":
                render.mount(msg["path"], msg["routeInfo"])
            elif msg["type"] == "navigate":
                render.navigate(msg["path"], msg["routeInfo"])
            elif msg["type"] == "callback":
                render.execute_callback(msg["path"], msg["callback"], msg["args"])
            elif msg["type"] == "unmount":
                render.unmount(msg["path"])
                self.channels.remove_route(render.id, msg["path"])
            elif msg["type"] == "api_result":
                render.handle_api_result(dict(msg))
            else:
                logger.warning("Unknown message type received: %s", msg)
            return Ok()

        with PulseContext.update(session=session, render=render):
            try:
                res = self.middleware.message(
                    data=msg,
                    session=session.data,
                    next=_next,
                )
            except Exception:
                logger.exception("Error in message middleware")
                return

            if isinstance(res, Deny):
                path = cast(str, msg.get("path", "api_response"))
                render.report_error(
                    path,
                    "server",
                    Exception("Request denied by server"),
                    {"kind": "deny"},
                )

    def _handle_channel_message(
        self, render: RenderSession, session: UserSession, msg: ClientChannelMessage
    ) -> None:
        if msg.get("responseTo"):
            msg = cast(ClientChannelResponseMessage, msg)
            self.channels.handle_client_response(msg)
        else:
            channel_id = str(msg.get("channel", ""))
            msg = cast(ClientChannelRequestMessage, msg)

            def _next() -> Ok[Any]:
                return Ok(
                    self.channels.handle_client_event(
                        render=render, session=session, message=msg
                    )
                )

            with PulseContext.update(session=session, render=render):
                res = self.middleware.channel(
                    channel_id=channel_id,
                    event=msg.get("event", ""),
                    payload=msg.get("payload"),
                    request_id=msg.get("requestId"),
                    session=session.data,
                    next=_next,
                )

            if isinstance(res, Deny):
                if req_id := msg.get("requestId"):
                    self.channels.send_error(channel_id, req_id, "Denied")

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
                    else:
                        session = UserSession(sid, data, self)
                        self.user_sessions[sid] = session
                        return session
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
        self, rid: str, session: UserSession, *, client_address: Optional[str] = None
    ):
        if rid in self.render_sessions:
            raise ValueError(f"RenderSession {rid} already exists")
        render = RenderSession(
            rid,
            self.routes,
            server_address=self.server_address,
            client_address=client_address,
        )
        self.render_sessions[rid] = render
        self._render_to_user[rid] = session.sid
        self._user_to_render[session.sid].append(rid)
        return render

    def close_render(self, rid: str):
        render = self.render_sessions.get(rid)
        if render is not None:
            self.channels.remove_render(rid)
        render = self.render_sessions.pop(rid, None)
        if not render:
            return
        sid = self._render_to_user.pop(rid)
        session = self.user_sessions[sid]
        self.forms.remove_render(rid)
        render.close()
        self._user_to_render[session.sid].remove(rid)

        if len(self._user_to_render[session.sid]) == 0:
            later(60, self.close_session_if_inactive, sid)

    def close_session(self, sid: str):
        session = self.user_sessions.pop(sid, None)
        self._user_to_render.pop(sid, None)
        if session:
            session.dispose()

    def close_session_if_inactive(self, sid: str):
        if len(self._user_to_render[sid]) == 0:
            self.close_session(sid)

    def refresh_cookies(self, sid: str):
        # If the session is currently inside an HTTP request, we don't need to schedule
        # set-cookies via WS; cookies will be attached on the HTTP response.
        if sid in self._sessions_in_request:
            return
        sess = self.user_sessions.get(sid)
        render_ids = self._user_to_render[sid]
        if not sess or len(render_ids) == 0:
            return

        render = None
        for rid in render_ids:
            candidate = self.render_sessions[rid]
            if candidate.connected:
                render = candidate
                break
        if render is None:
            return  # no active render for this user session

        # We don't want to wait for this to resolve
        create_task(render.call_api("/set-cookies", method="GET"))
        sess._scheduled_cookie_refresh = True


def add_react_components(
    routes: Sequence[Route | Layout], components: list[ReactComponent]
):
    for route in routes:
        if route.components is None:
            route.components = components
        if route.children:
            add_react_components(route.children, components)


def add_css_modules(routes: Sequence[Route | Layout], modules: list[CssModule]):
    for route in routes:
        if route.css_modules is None:
            route.css_modules = modules
        if route.children:
            add_css_modules(route.children, modules)


def add_css_imports(routes: Sequence[Route | Layout], imports: list[CssImport]):
    for route in routes:
        if route.css_imports is None:
            route.css_imports = imports
        if route.children:
            add_css_imports(route.children, imports)
