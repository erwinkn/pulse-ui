"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import IntEnum
from functools import wraps
from typing import Any, Callable, TypeVar, cast, override

import socketio
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

from pulse.codegen.codegen import Codegen, CodegenConfig
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.cookies import (
	Cookie,
	compute_cookie_secure,
	session_cookie,
)
from pulse.env import PulseEnv
from pulse.env import env as envvars
from pulse.helpers import (
	find_available_port,
)
from pulse.hooks.core import hooks
from pulse.messages import (
	ClientChannelMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ClientMessage,
	ClientPulseMessage,
	Prerender,
	PrerenderPayload,
	ServerInitMessage,
	ServerMessage,
	ServerNavigateToMessage,
)
from pulse.middleware import (
	ConnectResponse,
	Deny,
	MiddlewareStack,
	NotFound,
	Ok,
	PrerenderResponse,
	PulseMiddleware,
	Redirect,
)
from pulse.origins import normalize_http_origin
from pulse.plugin import Plugin
from pulse.proxy import WebProxy, WebProxyConfig
from pulse.reactive_extensions import unwrap
from pulse.render_session import RenderSession
from pulse.request import PulseRequest
from pulse.routing import Layout, Route, RouteTree, ensure_absolute_path
from pulse.scheduling import TaskRegistry, TimerHandleLike, TimerRegistry
from pulse.serializer import Serialized, deserialize, serialize
from pulse.user_session import (
	CookieSessionStore,
	SessionStore,
	UserSession,
	new_sid,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")
FRAMEWORK_API_PREFIX = "/_pulse"
MAX_PENDING_SOCKET_MESSAGES = 100
PULSE_ENDPOINT_UNWRAP_MARKER = "__pulse_endpoint_unwrap__"


class AppStatus(IntEnum):
	"""Application lifecycle status.

	Attributes:
		created: App instance created but not yet initialized.
		initialized: App.setup() has been called, routes configured.
		running: App is actively serving requests.
		draining: App is shutting down, draining connections.
		stopped: App has been fully stopped.
	"""

	created = 0
	initialized = 1
	running = 2
	draining = 3
	stopped = 4


@dataclass
class ConnectionStatusConfig:
	"""
	Configuration for connection status message delays.

	Attributes:
			initial_connecting_delay: Delay in seconds before showing "Connecting..." message
					on initial connection attempt. Default: 2.0
			initial_error_delay: Additional delay in seconds before showing error message
					on initial connection attempt (after connecting message). Default: 8.0
			reconnect_error_delay: Delay in seconds before showing error message when
					reconnecting after losing connection. Default: 8.0
	"""

	initial_connecting_delay: float = 2.0
	initial_error_delay: float = 8.0
	reconnect_error_delay: float = 8.0


class PulseAPIRoute(APIRoute):
	def __init__(
		self,
		path: str,
		endpoint: Callable[..., Any],
		**kwargs: Any,
	) -> None:
		super().__init__(path, _wrap_fastapi_endpoint(endpoint), **kwargs)


class PulseFastAPI(FastAPI):
	@override
	def include_router(self, router: APIRouter, **kwargs: Any) -> None:
		_wrap_router_endpoints(router)
		super().include_router(router, **kwargs)


def _wrap_router_endpoints(router: APIRouter) -> None:
	for route in router.routes:
		if isinstance(route, APIRoute):
			route.endpoint = _wrap_fastapi_endpoint(route.endpoint)


def _wrap_fastapi_endpoint(endpoint: Callable[..., Any]) -> Callable[..., Any]:
	if endpoint.__dict__.get(PULSE_ENDPOINT_UNWRAP_MARKER):
		return endpoint

	if asyncio.iscoroutinefunction(endpoint):

		@wraps(endpoint)
		async def async_endpoint(*args: Any, **kwargs: Any) -> Any:
			return _unwrap_fastapi_response(await endpoint(*args, **kwargs))

		async_endpoint.__dict__[PULSE_ENDPOINT_UNWRAP_MARKER] = True
		return async_endpoint

	@wraps(endpoint)
	def sync_endpoint(*args: Any, **kwargs: Any) -> Any:
		return _unwrap_fastapi_response(endpoint(*args, **kwargs))

	sync_endpoint.__dict__[PULSE_ENDPOINT_UNWRAP_MARKER] = True
	return sync_endpoint


def _unwrap_fastapi_response(value: Any) -> Any:
	if isinstance(value, Response):
		return value
	return unwrap(value, untrack=True)


class _RouteFallback:
	"""Dispatch unmatched HTTP/WebSocket traffic without entering FastAPI."""

	app: FastAPI
	fallback: ASGIApp

	def __init__(self, app: FastAPI, fallback: ASGIApp) -> None:
		self.app = app
		self.fallback = fallback

	def _matches_app(self, scope: Scope) -> bool:
		for route in self.app.router.routes:
			match, _ = route.matches(scope)
			if match is not Match.NONE:
				return True

		# Preserve Starlette's redirect-slashes behavior instead of proxying a
		# missing/extra trailing slash that belongs to an application route.
		path = scope.get("path", "")
		if path != "/":
			redirect_scope = dict(scope)
			redirect_scope["path"] = (
				path.rstrip("/") if path.endswith("/") else f"{path}/"
			)
			for route in self.app.router.routes:
				match, _ = route.matches(redirect_scope)
				if match is not Match.NONE:
					return True
		return False

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] not in ("http", "websocket") or self._matches_app(scope):
			await self.app(scope, receive, send)
			return
		await self.fallback(scope, receive, send)


class App:
	"""Main Pulse application class.

	Creates a server that handles routing, sessions, and WebSocket connections.
	Similar to FastAPI, users create an App instance and define their routes.

	Args:
		routes: Route definitions for the application.
		codegen: Code generation settings for React Router output.
		middleware: Request middleware, either a single middleware or sequence.
		plugins: Application plugins that can contribute routes, middleware,
			and lifecycle hooks.
		cookie: Session cookie configuration.
		session_store: Session storage backend. Defaults to CookieSessionStore.
		public_origin: Optional canonical browser-visible origin for server-side
			integrations that require absolute URLs.
		not_found: Path for 404 page. Defaults to "/not-found".
		proxy: Optional internal web proxy tuning.
		socketio_options: Extra options for the Socket.IO server (e.g.
			cors_allowed_origins when a fronting proxy cannot forward
			Host/X-Forwarded-Proto).
		session_timeout: Session cleanup timeout in seconds. Defaults to 60.0.
		connection_status: Connection status UI timing configuration.

	Attributes:
		env: Current environment ("dev", "ci", or "prod").
		status: Current application lifecycle status.
		routes: Parsed route tree containing all registered routes.
		fastapi: Underlying FastAPI instance.
		asgi: ASGI application (includes Socket.IO).

	Example:
		```python
		import pulse as ps

		app = ps.App(
				routes=[
						ps.Route("/", render=home),
						ps.Route("/users/:id", render=user_detail),
				],
				session_timeout=120.0,
		)

		if __name__ == "__main__":
				app.run(port=8000)
		```
	"""

	env: PulseEnv
	status: AppStatus
	public_origin: str | None
	plugins: list[Plugin]
	routes: RouteTree
	not_found: str
	user_sessions: dict[str, UserSession]
	render_sessions: dict[str, RenderSession]
	session_store: SessionStore | CookieSessionStore
	cookie: Cookie
	codegen: Codegen
	fastapi: FastAPI
	sio: socketio.AsyncServer
	asgi: ASGIApp
	middleware: MiddlewareStack
	_user_to_render: dict[str, list[str]]
	_render_to_user: dict[str, str]
	_sessions_in_request: dict[str, int]
	_socket_to_render: dict[str, str]
	_render_to_socket: dict[str, str]
	_connecting_sockets: set[str]
	_pending_socket_messages: dict[str, list[Serialized]]
	_render_cleanups: dict[str, TimerHandleLike]
	_render_message_locks: dict[str, asyncio.Lock]
	_tasks: TaskRegistry
	_timers: TimerRegistry
	_proxy: WebProxy | None
	proxy: WebProxyConfig
	session_timeout: float
	connection_status: ConnectionStatusConfig
	render_loop_limit: int
	prerender_queue_timeout: float
	disconnect_queue_timeout: float

	def __init__(
		self,
		routes: Sequence[Route | Layout] | None = None,
		codegen: CodegenConfig | None = None,
		middleware: PulseMiddleware | Sequence[PulseMiddleware] | None = None,
		plugins: Sequence[Plugin] | None = None,
		cookie: Cookie | None = None,
		session_store: SessionStore | CookieSessionStore | None = None,
		public_origin: str | None = None,
		not_found: str = "/not-found",
		proxy: WebProxyConfig | None = None,
		socketio_options: dict[str, Any] | None = None,
		session_timeout: float = 60.0,
		prerender_queue_timeout: float = 60.0,
		disconnect_queue_timeout: float = 300.0,
		connection_status: ConnectionStatusConfig | None = None,
		render_loop_limit: int = 50,
	):
		self.env = envvars.pulse_env
		self.proxy = proxy or WebProxyConfig()
		self.status = AppStatus.created
		configured_public_origin = (
			public_origin if public_origin is not None else envvars.public_origin
		)
		self.public_origin = (
			normalize_http_origin(
				configured_public_origin,
				name="public_origin",
				require_https=self.env in ("prod", "ci"),
			)
			if configured_public_origin is not None
			else None
		)

		# Resolve and store plugins (sorted by priority, highest first)
		self.plugins = []
		if plugins:
			self.plugins = sorted(
				list(plugins), key=lambda p: getattr(p, "priority", 0), reverse=True
			)

		# Build the complete route list from constructor args and plugins
		all_routes: list[Route | Layout] = list(routes or [])
		# Add plugin routes after user-defined routes
		for plugin in self.plugins:
			all_routes.extend(plugin.routes())
		self._validate_reserved_routes(all_routes)

		# RouteTree filters routes based on dev flag and environment during construction
		self.routes = RouteTree(all_routes)
		self.not_found = not_found
		# Default not-found path for client-side navigation on not_found()
		# Users can override via App(..., not_found_path="/my-404") in future
		self.user_sessions = {}
		self.render_sessions = {}
		self.session_store = session_store or CookieSessionStore()
		self.cookie = cookie or session_cookie()

		self._user_to_render = defaultdict(list)
		self._render_to_user = {}
		self._sessions_in_request = {}
		# Map websocket sid <-> renderId for message routing. A render has at
		# most one current socket; the reverse map identifies it so a stale
		# socket's disconnect cannot tear down a newer connection.
		self._socket_to_render = {}
		self._render_to_socket = {}
		self._connecting_sockets = set()
		self._pending_socket_messages = {}
		# Map render_id -> cleanup timer handle for timeout-based expiry
		self._render_cleanups = {}
		self._render_message_locks = {}
		self._tasks = TaskRegistry(name="app")
		self._timers = TimerRegistry(tasks=self._tasks, name="app")
		self._proxy = None
		self.session_timeout = session_timeout
		self.prerender_queue_timeout = prerender_queue_timeout
		self.disconnect_queue_timeout = disconnect_queue_timeout
		self.connection_status = connection_status or ConnectionStatusConfig()
		self.render_loop_limit = render_loop_limit

		self.codegen = Codegen(
			self.routes,
			config=codegen or CodegenConfig(),
		)

		self.fastapi = PulseFastAPI(
			title="Pulse UI Server",
			lifespan=self.fastapi_lifespan,
		)
		self.fastapi.router.route_class = PulseAPIRoute
		self.sio = socketio.AsyncServer(
			async_mode="asgi",
			**{"async_handlers": False, **(socketio_options or {})},
		)
		self.asgi = socketio.ASGIApp(
			self.sio,
			self.fastapi,
			socketio_path=f"{FRAMEWORK_API_PREFIX}/socket.io",
		)

		if middleware is None:
			mw_stack: list[PulseMiddleware] = []
		elif isinstance(middleware, PulseMiddleware):
			mw_stack = [middleware]
		else:
			mw_stack = list(middleware)

		# Let plugins contribute middleware (in plugin priority order)
		for plugin in self.plugins:
			mw_stack.extend(plugin.middleware())

		self.middleware = MiddlewareStack(mw_stack)

	def _validate_reserved_routes(self, routes: Sequence[Route | Layout]) -> None:
		def _walk(
			nodes: Sequence[Route | Layout],
			ancestors: list[str] | None = None,
		) -> None:
			ancestors = [] if ancestors is None else ancestors
			for node in nodes:
				segments = (
					[*ancestors, node.path] if isinstance(node, Route) else [*ancestors]
				)
				path = ensure_absolute_path("/".join(part for part in segments if part))
				if path == FRAMEWORK_API_PREFIX or path.startswith(
					f"{FRAMEWORK_API_PREFIX}/"
				):
					raise ValueError(
						f"Routes under '{FRAMEWORK_API_PREFIX}/*' are reserved for Pulse framework endpoints."
					)
				_walk(node.children, segments)

		_walk(routes)

	@asynccontextmanager
	async def fastapi_lifespan(self, _: FastAPI):
		try:
			if isinstance(self.session_store, SessionStore):
				await self.session_store.init()
		except Exception:
			logger.exception("Error during SessionStore.init()")

		# Call plugin on_startup hooks before serving
		for plugin in self.plugins:
			plugin.on_startup(self)

		if envvars.web_upstream:
			logger.info("Proxying web requests to %s", envvars.web_upstream)

		try:
			yield
		finally:
			try:
				await self.close()
			except Exception:
				logger.exception("Error during App.close()")

			try:
				if isinstance(self.session_store, SessionStore):
					await self.session_store.close()
			except Exception:
				logger.exception("Error during SessionStore.close()")

	def run_codegen(self) -> None:
		"""Generate React Router code for all routes.

		Generates TypeScript/JSX files for React Router integration based on
		the application's route definitions.

		"""
		if envvars.codegen_disabled:
			return
		self.codegen.generate_all(
			connection_status=self.connection_status,
		)

	def asgi_factory(self) -> ASGIApp:
		"""ASGI factory for production deployment.

		Called on each uvicorn reload. Initializes code generation and the app.

		Returns:
			The ASGI application instance (includes Socket.IO).

		"""
		self.run_codegen()
		self.setup()
		self.status = AppStatus.running

		return self.asgi

	def run(
		self,
		address: str = "localhost",
		port: int = 8000,
		find_port: bool = True,
		reload: bool = True,
	) -> None:
		"""Start the development server with uvicorn.

		Args:
			address: Host address to bind to. Defaults to "localhost".
			port: Port number to listen on. Defaults to 8000.
			find_port: If True, automatically find an available port if the
				specified port is in use. Defaults to True.
			reload: If True, enable auto-reload on file changes. Defaults to True.
		"""
		if find_port:
			port = find_available_port(port)

		uvicorn.run(self.asgi_factory, reload=reload)

	def setup(self) -> None:
		"""Initialize the app.

		Configures FastAPI routes, middleware, and Socket.IO handlers.
		Called automatically by asgi_factory().

		Note:
			This method is idempotent - calling it multiple times on an already
			initialized app will log a warning and return early.
		"""
		if self.status >= AppStatus.initialized:
			logger.warning("Called App.setup() on an already initialized application")
			return
		proxy_handler = (
			WebProxy(web_upstream, config=self.proxy)
			if (web_upstream := envvars.web_upstream)
			else None
		)

		PULSE_CONTEXT.set(PulseContext(app=self))

		hooks.lock()

		if self.cookie.secure is None:
			self.cookie.secure = compute_cookie_secure(self.env, self.public_origin)
		elif self.env in ("prod", "ci") and not self.cookie.secure:
			raise RuntimeError("Refusing to use insecure cookies in prod/ci")

		# Mount PulseContext for all FastAPI routes (no route info). Other API
		# routes / middleware should be added at the module-level, which means
		# this middleware will wrap all of them.
		@self.fastapi.middleware("http")
		async def session_middleware(  # pyright: ignore[reportUnusedFunction]
			request: Request, call_next: Callable[[Request], Awaitable[Response]]
		):
			# Session cookie handling
			cookie = self.cookie.get_from_fastapi(request)
			session = await self.get_or_create_session(cookie)
			self._sessions_in_request[session.sid] = (
				self._sessions_in_request.get(session.sid, 0) + 1
			)
			render_id = request.headers.get("x-pulse-render-id")
			render = self._get_render_for_session(render_id, session)
			try:
				with PulseContext.update(session=session, render=render):
					res: Response = await call_next(request)
				await session.handle_response(res)
				return res
			except RuntimeError as exc:
				# Client disconnected before response was sent. This happens when
				# ASGI handlers (like the proxy) return early on disconnect without
				# sending a response, which is valid ASGI but breaks BaseHTTPMiddleware.
				if "No response returned" in str(exc):
					return Response(status_code=499)
				raise
			finally:
				self._sessions_in_request[session.sid] -= 1
				if self._sessions_in_request[session.sid] == 0:
					del self._sessions_in_request[session.sid]
					# Sessions without render sessions would otherwise be retained
					# forever: cookie-less clients (bots, health checks) mint one
					# per request. Their state lives in the cookie/session store,
					# so dropping the in-memory object is safe.
					self.close_session_if_inactive(session.sid)

		@self.fastapi.get(f"{FRAMEWORK_API_PREFIX}/health")
		def healthcheck():  # pyright: ignore[reportUnusedFunction]
			return {"health": "ok", "message": "Pulse server is running"}

		@self.fastapi.get(f"{FRAMEWORK_API_PREFIX}/set-cookies")
		def set_cookies():  # pyright: ignore[reportUnusedFunction]
			return {"health": "ok", "message": "Cookies updated"}

		# RouteInfo is the request body
		@self.fastapi.post(f"{FRAMEWORK_API_PREFIX}/prerender")
		async def prerender(payload: PrerenderPayload, request: Request):  # pyright: ignore[reportUnusedFunction]
			"""
			POST /prerender
			Body: { paths: string[], routeInfo: RouteInfo, ttlSeconds?: number }
			Headers: X-Pulse-Render-Id (optional, for render session reuse)
			Returns: { renderId: string, <path>: VDOM, ... }
			"""
			session = PulseContext.get().session
			if session is None:
				raise RuntimeError("Internal error: couldn't resolve user session")
			paths = payload.get("paths") or []
			if len(paths) == 0:
				raise HTTPException(
					status_code=400, detail="'paths' must be a non-empty list"
				)
			paths = [ensure_absolute_path(path) for path in paths]
			payload["paths"] = paths
			route_info = payload.get("routeInfo")

			# Reuse render session from header (set by middleware) or create new one
			render = PulseContext.get().render
			if render is not None:
				render_id = render.id
			else:
				# Create new render session
				render_id = new_sid()
				render = self.create_render(render_id, session)
			# Schedule cleanup timeout (will cancel/reschedule on activity)
			if not render.connected:
				self._schedule_render_cleanup(render_id)

			def _normalize_prerender_result(
				captured: ServerInitMessage | ServerNavigateToMessage,
			) -> Ok[ServerInitMessage] | Redirect | NotFound:
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
				# Call top-level prerender middleware, which wraps the route processing
				async def _process_routes() -> PrerenderResponse:
					result_data: Prerender = {
						"views": {},
						"directives": {
							"headers": {"X-Pulse-Render-Id": render_id},
							"query": {},
							"socketio": {
								"auth": {"render_id": render_id},
								"query": {},
							},
						},
					}

					captured = render.prerender(paths, route_info)

					for p in paths:
						res = _normalize_prerender_result(captured[p])
						if isinstance(res, Ok):
							# Aggregate results
							result_data["views"][p] = res.payload
						elif isinstance(res, Redirect):
							# Return redirect immediately
							return Redirect(path=res.path or "/")
						elif isinstance(res, NotFound):
							# Return not found immediately
							return NotFound()
						else:
							raise ValueError("Unexpected prerender response:", res)

					return Ok(result_data)

				result = await self.middleware.prerender(
					payload=payload,
					request=PulseRequest.from_fastapi(request),
					session=session.data,
					next=_process_routes,
				)

			# Handle redirect/notFound responses
			if isinstance(result, Redirect):
				resp = JSONResponse({"redirect": result.path})
				await session.handle_response(resp)
				return resp
			if isinstance(result, NotFound):
				resp = JSONResponse({"notFound": True})
				await session.handle_response(resp)
				return resp

			# Handle Ok result - serialize the payload (PrerenderResultData)
			if isinstance(result, Ok):
				resp = JSONResponse(serialize(result.payload))
				await session.handle_response(resp)
				return resp

			# Fallback (shouldn't happen)
			raise ValueError("Unexpected prerender result type")

		@self.fastapi.post(f"{FRAMEWORK_API_PREFIX}/forms/{{render_id}}/{{form_id}}")
		async def handle_form_submit(  # pyright: ignore[reportUnusedFunction]
			render_id: str, form_id: str, request: Request
		) -> Response:
			session = PulseContext.get().session
			if session is None:
				raise RuntimeError("Internal error: couldn't resolve user session")

			render = self.render_sessions.get(render_id)
			if not render:
				raise HTTPException(status_code=410, detail="Render session expired")

			return await render.forms.handle_submit(form_id, request, session)

		# Call on_setup hooks after FastAPI routes/middleware are in place
		for plugin in self.plugins:
			plugin.on_setup(self)

		# Optional web composition. The fallback lives outside FastAPI so web
		# pages/assets do not create Pulse sessions. FastAPI routes still win.
		if proxy_handler is not None:
			self._proxy = proxy_handler
			fallback = _RouteFallback(self.fastapi, proxy_handler)
			self.asgi = socketio.ASGIApp(
				self.sio,
				fallback,
				socketio_path=f"{FRAMEWORK_API_PREFIX}/socket.io",
			)

		@self.sio.event
		async def connect(  # pyright: ignore[reportUnusedFunction]
			sid: str, environ: dict[str, Any], auth: dict[str, str] | None
		):
			# Expect renderId during websocket auth and require a valid user session
			rid = auth.get("render_id") if auth else None
			if rid:
				self._connecting_sockets.add(sid)
			try:
				await _connect_socket(sid, environ, auth, rid)
			except Exception:
				self._connecting_sockets.discard(sid)
				self._pending_socket_messages.pop(sid, None)
				self._socket_to_render.pop(sid, None)
				if rid and self._render_to_socket.get(rid) == sid:
					del self._render_to_socket[rid]
				raise
			await self._drain_pending_socket_messages(sid)

		async def _connect_socket(  # pyright: ignore[reportUnusedFunction]
			sid: str,
			environ: dict[str, Any],
			auth: dict[str, str] | None,
			rid: str | None,
		):
			# Parse cookies from environ and ensure a session exists
			cookie = self.cookie.get_from_socketio(environ)
			if cookie is None:
				raise ConnectionRefusedError("Socket connect missing cookie")
			session = await self.get_or_create_session(cookie)

			if not rid:
				# Still refuse connections without a renderId
				self.close_session_if_inactive(session.sid)
				raise ConnectionRefusedError(
					f"Socket connect missing render_id session={session.sid}"
				)

			# Allow reconnects where the provided renderId no longer exists by creating a new RenderSession
			render = self.render_sessions.get(rid)
			created_render = render is None
			if render is None:
				# The client will try to attach to a non-existing RouteMount, which will cause a reload down the line
				render = self.create_render(rid, session)
			else:
				owner = self._render_to_user.get(render.id)
				if owner != session.sid:
					self.close_session_if_inactive(session.sid)
					raise ConnectionRefusedError(
						f"Socket connect session mismatch render={render.id} "
						+ f"owner={owner} session={session.sid}"
					)

			# Authorize before binding the socket. A denied (re)connect must not
			# rebind or tear down an existing render that another live socket may
			# still be using; only the render we created for this attempt is ours
			# to clean up.
			connect_error: Exception | None = None
			with PulseContext.update(session=session, render=render):

				async def _next():
					return Ok(None)

				def _normalize_connect_response(res: Any) -> ConnectResponse:
					if isinstance(res, (Ok, Deny)):
						return res  # type: ignore[return-value]
					# Treat any other value as allow
					return Ok(None)

				try:
					res = await self.middleware.connect(
						request=PulseRequest.from_socketio_environ(environ, auth),
						session=session.data,
						next=_next,
					)
					res = _normalize_connect_response(res)
				except Exception as exc:
					# Treat a middleware error as allow, but surface it to the
					# client once the socket is bound (see below).
					connect_error = exc
					res = Ok(None)
				if isinstance(res, Deny):
					if created_render:
						self.close_render(rid)
					else:
						self.close_session_if_inactive(session.sid)
					raise ConnectionRefusedError("Socket connection denied")

				# Bind the socket inside the session context so query resume
				# (and recreated interval effects) capture the same
				# (session, render) context as initial fetches.
				def on_message(message: ServerMessage):
					payload = serialize(message)
					# `serialize` returns a tuple, which socket.io will mistake for multiple arguments
					payload = list(payload)
					self._tasks.create_task(
						self.sio.emit("message", list(payload), to=sid)
					)

				render.connect(on_message)
				# Map socket sid to renderId for message routing. If the client
				# reconnected before the old socket's disconnect fired, unmap the
				# old socket so its late disconnect can't tear down this connection.
				old_sid = self._render_to_socket.get(rid)
				if old_sid is not None and old_sid != sid:
					self._socket_to_render.pop(old_sid, None)
				self._socket_to_render[sid] = rid
				self._render_to_socket[rid] = sid

				# Cancel any pending cleanup since session is now connected
				self._cancel_render_cleanup(rid)

				# Surface any connect-middleware error now that the socket is bound
				# (reported pre-bind it would be dropped for a fresh render).
				if connect_error is not None:
					render.report_error("/", "connect", connect_error)

		@self.sio.event
		def disconnect(sid: str):  # pyright: ignore[reportUnusedFunction]
			self._connecting_sockets.discard(sid)
			self._pending_socket_messages.pop(sid, None)
			rid = self._socket_to_render.pop(sid, None)
			# Only the render's current socket may disconnect it; a stale
			# socket's late disconnect must not tear down a newer connection.
			if rid is not None and self._render_to_socket.get(rid) == sid:
				del self._render_to_socket[rid]
				render = self.render_sessions.get(rid)
				if render:
					render.disconnect()
					# Schedule cleanup after timeout (will keep session alive for reuse)
					self._schedule_render_cleanup(rid)

		@self.sio.event
		async def message(sid: str, data: Serialized):  # pyright: ignore[reportUnusedFunction]
			await self._handle_socket_message(sid, data)

		self.status = AppStatus.initialized

	def _cancel_render_cleanup(self, rid: str):
		"""Cancel any pending cleanup task for a render session."""
		cleanup_handle = self._render_cleanups.pop(rid, None)
		if cleanup_handle:
			if not cleanup_handle.cancelled():
				cleanup_handle.cancel()
			self._timers.discard(cleanup_handle)

	def _schedule_render_cleanup(self, rid: str):
		"""Schedule cleanup of a RenderSession after the configured timeout."""
		render = self.render_sessions.get(rid)
		if render is None:
			return
		# Don't schedule cleanup for connected sessions (they stay alive)
		if render.connected:
			return

		# Cancel any existing cleanup task for this render session
		self._cancel_render_cleanup(rid)

		# Schedule new cleanup task
		def _cleanup():
			render = self.render_sessions.get(rid)
			if render is None:
				return
			# Only cleanup if not connected (if connected, keep it alive)
			if not render.connected:
				logger.info(
					f"RenderSession {rid} expired after {self.session_timeout}s timeout"
				)
				self.close_render(rid)

		handle = self._timers.later(self.session_timeout, _cleanup)
		self._render_cleanups[rid] = handle

	async def _handle_socket_message(self, sid: str, data: Serialized) -> None:
		if sid in self._connecting_sockets:
			self._queue_pending_socket_message(sid, data)
			return
		await self._process_socket_message(sid, data)

	def _queue_pending_socket_message(self, sid: str, data: Serialized) -> None:
		queue = self._pending_socket_messages.setdefault(sid, [])
		if len(queue) >= MAX_PENDING_SOCKET_MESSAGES:
			logger.warning(
				"Dropping socket message for %s while connect is pending; queue is full",
				sid,
			)
			return
		queue.append(data)

	async def _drain_pending_socket_messages(self, sid: str) -> None:
		try:
			while pending := self._pending_socket_messages.pop(sid, []):
				for data in pending:
					await self._process_socket_message(sid, data)
		finally:
			self._connecting_sockets.discard(sid)

	async def _process_socket_message(self, sid: str, data: Serialized) -> None:
		rid = self._socket_to_render.get(sid)
		if not rid:
			return
		msg = cast(ClientMessage, deserialize(data))
		lock = self._render_message_locks.setdefault(rid, asyncio.Lock())
		async with lock:
			render = self.render_sessions.get(rid)
			if render is None:
				return
			owner_sid = self._render_to_user.get(rid)
			if owner_sid is None:
				return
			session = self.user_sessions.get(owner_sid)
			if session is None:
				return
			# Cancel any leftover cleanup for connected sessions. Never cancel
			# for disconnected renders: nothing would reschedule it and the
			# session would survive past its timeout.
			if render.connected:
				self._cancel_render_cleanup(rid)
			try:
				if msg["type"] == "channel_message":
					await self._handle_channel_message(render, session, msg)
				else:
					await self._handle_pulse_message(render, session, msg)
			except Exception as e:
				path = msg.get("path", "")
				render.report_error(path, "server", e)

	async def _handle_pulse_message(
		self, render: RenderSession, session: UserSession, msg: ClientPulseMessage
	) -> None:
		async def _next() -> Ok[None]:
			if msg["type"] == "attach":
				attached = render.attach(msg["path"], msg["routeInfo"])
				attach_id = msg.get("attachId")
				if attached and isinstance(attach_id, str):
					render.send(
						{
							"type": "attach_ack",
							"path": msg["path"],
							"attachId": attach_id,
						}
					)
			elif msg["type"] == "update":
				render.update_route(msg["path"], msg["routeInfo"])
			elif msg["type"] == "callback":
				render.execute_callback(msg["path"], msg["callback"], msg["args"])
			elif msg["type"] == "detach":
				render.detach(msg["path"])
				render.channels.remove_route(msg["path"])
			elif msg["type"] == "api_result":
				render.handle_api_result(dict(msg))
			elif msg["type"] == "js_result":
				render.handle_js_result(dict(msg))
			else:
				logger.warning("Unknown message type received: %s", msg)
			return Ok()

		def _normalize_message_response(res: Any) -> Ok[None] | Deny:
			if isinstance(res, (Ok, Deny)):
				return res  # type: ignore[return-value]
			# Treat any other value as allow
			return Ok(None)

		with PulseContext.update(session=session, render=render):
			try:
				res = await self.middleware.message(
					data=msg,
					session=session.data,
					next=_next,
				)
				res = _normalize_message_response(res)
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

	async def _handle_channel_message(
		self, render: RenderSession, session: UserSession, msg: ClientChannelMessage
	) -> None:
		if msg.get("responseTo"):
			msg = cast(ClientChannelResponseMessage, msg)
			render.channels.handle_client_response(msg)
		else:
			channel_id = str(msg.get("channel", ""))
			msg = cast(ClientChannelRequestMessage, msg)

			async def _next() -> Ok[None]:
				render.channels.handle_client_event(
					render=render, session=session, message=msg
				)
				return Ok(None)

			def _normalize_message_response(res: Any) -> Ok[None] | Deny:
				if isinstance(res, (Ok, Deny)):
					return res  # type: ignore[return-value]
				# Treat any other value as allow
				return Ok(None)

			with PulseContext.update(session=session, render=render):
				res = await self.middleware.channel(
					channel_id=channel_id,
					event=msg.get("event", ""),
					payload=msg.get("payload"),
					request_id=msg.get("requestId"),
					session=session.data,
					next=_next,
				)
				res = _normalize_message_response(res)

			if isinstance(res, Deny):
				if req_id := msg.get("requestId"):
					render.channels.send_error(channel_id, req_id, "Denied")

	def get_route(self, path: str):
		return self.routes.find(path)

	async def get_or_create_session(self, raw_cookie: str | None) -> UserSession:
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
			session.refresh_session_cookie(self)
			self.user_sessions[sid] = session
			return session

		if raw_cookie is not None and raw_cookie in self.user_sessions:
			return self.user_sessions[raw_cookie]

		# Server-backed store path
		assert isinstance(self.session_store, SessionStore)
		cookie_secure = self.cookie.secure
		if cookie_secure is None:
			raise RuntimeError(
				"Cookie.secure is not resolved. Ensure App.setup() ran before sessions."
			)
		if raw_cookie is not None:
			sid = raw_cookie
			data = await self.session_store.get(sid) or await self.session_store.create(
				sid
			)
			session = UserSession(sid, data, app=self)
			session.set_cookie(
				name=self.cookie.name,
				value=sid,
				secure=cookie_secure,
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
				secure=cookie_secure,
				samesite=self.cookie.samesite,
				max_age_seconds=self.cookie.max_age_seconds,
			)
		self.user_sessions[sid] = session
		return session

	def _get_render_for_session(
		self, render_id: str | None, session: UserSession
	) -> RenderSession | None:
		"""
		Get an existing render session for the given session, validating ownership.
		Returns None if render_id is None, render doesn't exist, or doesn't belong to session.
		"""
		if not render_id:
			return None
		render = self.render_sessions.get(render_id)
		if render is None:
			return None
		owner = self._render_to_user.get(render_id)
		if owner != session.sid:
			return None
		return render

	def create_render(self, rid: str, session: UserSession):
		if rid in self.render_sessions:
			raise ValueError(f"RenderSession {rid} already exists")
		render = RenderSession(
			rid,
			self.routes,
			prerender_queue_timeout=self.prerender_queue_timeout,
			# Development React StrictMode replays PulseView effects as
			# attach -> detach -> attach on first mount. Production should keep the
			# normal immediate detach semantics; only dev gets a tiny grace window.
			dev_strict_mode_detach_timeout=0.1 if self.env == "dev" else 0.0,
			disconnect_queue_timeout=self.disconnect_queue_timeout,
			render_loop_limit=self.render_loop_limit,
		)
		self.render_sessions[rid] = render
		self._render_to_user[rid] = session.sid
		self._user_to_render[session.sid].append(rid)
		return render

	def close_render(self, rid: str):
		# Cancel any pending cleanup task
		self._cancel_render_cleanup(rid)
		self._render_message_locks.pop(rid, None)
		socket_sid = self._render_to_socket.pop(rid, None)
		if socket_sid is not None:
			self._socket_to_render.pop(socket_sid, None)

		render = self.render_sessions.pop(rid, None)
		if not render:
			return
		sid = self._render_to_user.pop(rid)
		session = self.user_sessions[sid]
		render.close()
		self._user_to_render[session.sid].remove(rid)

		if len(self._user_to_render[session.sid]) == 0:
			self._timers.later(60, self.close_session_if_inactive, sid)

	def close_session(self, sid: str):
		session = self.user_sessions.pop(sid, None)
		self._user_to_render.pop(sid, None)
		if session:
			session.dispose()

	def close_session_if_inactive(self, sid: str):
		if sid in self._sessions_in_request:
			return
		if not self._user_to_render.get(sid):
			self.close_session(sid)

	async def reload_connected_clients(self) -> int:
		payload = list(serialize({"type": "reload"}))
		socket_ids = list(self._socket_to_render.keys())
		for socket_id in socket_ids:
			await self.sio.emit("message", payload, to=socket_id)
		return len(socket_ids)

	async def close(self):
		"""
		Close the app and clean up all sessions.
		This method is called automatically during shutdown.
		"""

		# Cancel all pending cleanup tasks
		for rid in list(self._render_cleanups.keys()):
			self._cancel_render_cleanup(rid)

		# Close all render sessions
		for rid in list(self.render_sessions.keys()):
			self.close_render(rid)

		# Close all user sessions
		for sid in list(self.user_sessions.keys()):
			self.close_session(sid)

		# Cancel any remaining app-level tasks/timers
		self._tasks.cancel_all()
		self._timers.cancel_all()
		if self._proxy is not None:
			try:
				await self._proxy.close()
			except Exception:
				logger.exception("Error during WebProxy.close()")

		# Update status
		self.status = AppStatus.stopped
		# Call plugin on_shutdown hooks before closing
		for plugin in self.plugins:
			try:
				plugin.on_shutdown(self)
			except Exception:
				logger.exception("Error during plugin.on_shutdown()")

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
		render.create_task(
			render.call_api(f"{FRAMEWORK_API_PREFIX}/set-cookies", method="GET"),
			name="cookies.refresh",
		)
		sess.scheduled_cookie_refresh = True
