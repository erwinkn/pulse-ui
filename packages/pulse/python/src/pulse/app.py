"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

import logging
import os
from collections import defaultdict
from collections.abc import Awaitable, Sequence
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import Any, Callable, Literal, TypeVar, cast

import socketio
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp

from pulse.codegen.codegen import Codegen, CodegenConfig
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.cookies import (
	Cookie,
	CORSOptions,
	compute_cookie_domain,
	cors_options,
	session_cookie,
)
from pulse.css import (
	CssImport,
	CssModule,
	registered_css_imports,
	registered_css_modules,
)
from pulse.env import (
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
	PulseEnv,
)
from pulse.env import env as envvars
from pulse.helpers import (
	create_task,
	find_available_port,
	get_client_address,
	get_client_address_socketio,
	later,
)
from pulse.hooks.core import hooks
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import (
	ClientChannelMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ClientMessage,
	ClientPulseMessage,
	PrerenderPayload,
	PrerenderResult,
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
from pulse.proxy import PulseProxy
from pulse.react_component import ReactComponent, registered_react_components
from pulse.render_session import RenderSession
from pulse.request import PulseRequest
from pulse.routing import Layout, Route, RouteTree
from pulse.serializer import Serialized, deserialize, serialize
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
	draining = 3
	stopped = 4


PulseMode = Literal["subdomains", "single-server"]


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

	env: PulseEnv
	mode: PulseMode
	status: AppStatus
	server_address: str | None
	dev_server_address: str
	internal_server_address: str | None
	api_prefix: str
	plugins: list[Plugin]
	routes: RouteTree
	not_found: str
	user_sessions: dict[str, UserSession]
	render_sessions: dict[str, RenderSession]
	session_store: SessionStore | CookieSessionStore
	cookie: Cookie
	cors: CORSOptions | None
	codegen: Codegen
	fastapi: FastAPI
	sio: socketio.AsyncServer
	asgi: ASGIApp
	middleware: MiddlewareStack
	_user_to_render: dict[str, list[str]]
	_render_to_user: dict[str, str]
	_sessions_in_request: dict[str, int]
	_socket_to_render: dict[str, str]

	def __init__(
		self,
		routes: Sequence[Route | Layout] | None = None,
		dev_routes: Sequence[Route | Layout] | None = None,
		codegen: CodegenConfig | None = None,
		middleware: PulseMiddleware | Sequence[PulseMiddleware] | None = None,
		plugins: Sequence[Plugin] | None = None,
		cookie: Cookie | None = None,
		session_store: SessionStore | None = None,
		server_address: str | None = None,
		dev_server_address: str = "http://localhost:8000",
		internal_server_address: str | None = None,
		not_found: str = "/not-found",
		# Deployment and integration options
		mode: PulseMode = "single-server",
		api_prefix: str = "/_pulse",
		cors: CORSOptions | None = None,
		fastapi: dict[str, Any] | None = None,
	):
		"""
		Initialize a new Pulse App.

		Args:
		    routes: Optional list of Route objects to register.
		    codegen: Optional codegen configuration.
		"""
		# Resolve mode from environment and expose on the app instance
		self.env = envvars.pulse_env
		self.mode = mode
		self.status = AppStatus.created
		# Persist the server address for use by sessions (API calls, etc.)
		self.server_address = server_address
		# Development server address (used in dev mode)
		self.dev_server_address = dev_server_address
		# Optional internal address used by server-side loader fetches
		self.internal_server_address = internal_server_address

		self.api_prefix = api_prefix

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
			if self.env == "dev":
				all_routes.extend(plugin.dev_routes())

		# Auto-add React components to all routes
		add_react_components(all_routes, registered_react_components())
		add_css_modules(all_routes, registered_css_modules())
		add_css_imports(all_routes, registered_css_imports())
		self.routes = RouteTree(all_routes)
		self.not_found = not_found
		# Default not-found path for client-side navigation on not_found()
		# Users can override via App(..., not_found_path="/my-404") in future
		self.user_sessions = {}
		self.render_sessions = {}
		self.session_store = session_store or CookieSessionStore()
		self.cookie = cookie or session_cookie(mode=self.mode)
		self.cors = cors

		self._user_to_render = defaultdict(list)
		self._render_to_user = {}
		self._sessions_in_request = {}
		# Map websocket sid -> renderId for message routing
		self._socket_to_render = {}

		self.codegen = Codegen(
			self.routes,
			config=codegen or CodegenConfig(),
		)

		self.fastapi = FastAPI(
			title="Pulse UI Server",
			lifespan=self.fastapi_lifespan,
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

		if self.mode == "single-server":
			react_server_address = envvars.react_server_address
			if react_server_address:
				logger.info(
					f"Single-server mode: React Router running at {react_server_address}"
				)
			else:
				logger.warning(
					"Single-server mode: PULSE_REACT_SERVER_ADDRESS not set."
				)

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

	def run_codegen(
		self, address: str | None = None, internal_address: str | None = None
	):
		# Allow the CLI to disable codegen in specific scenarios (e.g., prod server-only)
		if envvars.codegen_disabled:
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
			self.api_prefix,
		)

	def asgi_factory(self):
		"""
		ASGI factory for uvicorn. This is called on every reload.
		"""

		# In prod/ci, use the server_address provided to App(...).
		if self.env in ("prod", "ci"):
			if not self.server_address:
				raise RuntimeError(
					f"In {self.env}, please provide an explicit server_address to App(...)."
				)
			server_address = self.server_address
		# In dev, prefer env vars set by CLI (--address/--port), otherwise use dev_server_address.
		else:
			# In dev mode, check if CLI set PULSE_HOST/PULSE_PORT env vars
			# If env vars were explicitly set (not just defaults), use them
			host = os.environ.get(ENV_PULSE_HOST)
			port = os.environ.get(ENV_PULSE_PORT)
			if host is not None and port is not None:
				protocol = "http" if host in ("127.0.0.1", "localhost") else "https"
				server_address = f"{protocol}://{host}:{port}"
			else:
				server_address = self.dev_server_address

		# Use internal server address for server-side loader if provided; fallback to public
		internal_address = self.internal_server_address or server_address
		self.run_codegen(server_address, internal_address)
		self.setup(server_address)
		self.status = AppStatus.running

		# In single-server mode, the Pulse server acts as reverse proxy to the React server
		if self.mode == "single-server":
			return PulseProxy(
				self.asgi, lambda: envvars.react_server_address, self.api_prefix
			)
		return self.asgi

	def run(
		self,
		address: str = "localhost",
		port: int = 8000,
		find_port: bool = True,
		reload: bool = True,
	):
		if find_port:
			port = find_available_port(port)

		uvicorn.run(self.asgi_factory, reload=reload)

	def setup(self, server_address: str):
		if self.status >= AppStatus.initialized:
			logger.warning("Called App.setup() on an already initialized application")
			return

		self.server_address = server_address
		PULSE_CONTEXT.set(PulseContext(app=self))

		hooks.lock()

		# Compute cookie domain from deployment/server address if not explicitly provided
		if self.cookie.domain is None:
			self.cookie.domain = compute_cookie_domain(self.mode, self.server_address)

		# Add CORS middleware (configurable/overridable)
		if self.cors is not None:
			self.fastapi.add_middleware(CORSMiddleware, **self.cors)
		else:
			# Use deployment-specific CORS settings
			cors_config = cors_options(self.mode, self.server_address)
			print(f"CORS config: {cors_config}")
			self.fastapi.add_middleware(
				CORSMiddleware,
				**cors_config,
			)

		# Debug middleware to log CORS-related request details
		# @self.fastapi.middleware("http")
		# async def cors_debug_middleware(
		# 	request: Request, call_next: Callable[[Request], Awaitable[Response]]
		# ):
		# 	origin = request.headers.get("origin")
		# 	method = request.method
		# 	path = request.url.path
		# 	print(
		# 		f"[CORS Debug] {method} {path} | Origin: {origin} | "
		# 		+ f"Mode: {self.mode} | Server: {self.server_address}"
		# 	)
		# 	response = await call_next(request)
		# 	allow_origin = response.headers.get("access-control-allow-origin")
		# 	if allow_origin:
		# 		print(f"[CORS Debug] Response allows origin: {allow_origin}")
		# 	elif origin:
		# 		logger.warning(
		# 			f"[CORS Debug] Origin {origin} present but no Access-Control-Allow-Origin header set"
		# 		)
		# 	return response

		# Mount PulseContext for all FastAPI routes (no route info). Other API
		# routes / middleware should be added at the module-level, which means
		# this middleware will wrap all of them.
		@self.fastapi.middleware("http")
		async def session_middleware(  # pyright: ignore[reportUnusedFunction]
			request: Request, call_next: Callable[[Request], Awaitable[Response]]
		):
			# Skip session handling for CORS preflight requests
			if request.method == "OPTIONS":
				return await call_next(request)
			# Session cookie handling
			cookie = self.cookie.get_from_fastapi(request)
			session = await self.get_or_create_session(cookie)
			self._sessions_in_request[session.sid] = (
				self._sessions_in_request.get(session.sid, 0) + 1
			)
			render_id = request.headers.get("x-pulse-render-id")
			if render_id:
				render = self.render_sessions.get(render_id)
			else:
				render = None
			with PulseContext.update(session=session, render=render):
				res: Response = await call_next(request)
			session.handle_response(res)

			self._sessions_in_request[session.sid] -= 1
			if self._sessions_in_request[session.sid] == 0:
				del self._sessions_in_request[session.sid]

			return res

		# Apply prefix to all routes
		prefix = self.api_prefix

		@self.fastapi.get(f"{prefix}/health")
		def healthcheck():  # pyright: ignore[reportUnusedFunction]
			return {"health": "ok", "message": "Pulse server is running"}

		@self.fastapi.get(f"{prefix}/set-cookies")
		def set_cookies():  # pyright: ignore[reportUnusedFunction]
			return {"health": "ok", "message": "Cookies updated"}

		# RouteInfo is the request body
		@self.fastapi.post(f"{prefix}/prerender")
		async def prerender(payload: PrerenderPayload, request: Request):  # pyright: ignore[reportUnusedFunction]
			"""
			POST /prerender
			Body: { paths: string[], routeInfo: RouteInfo, ttlSeconds?: number, renderId?: string }
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
			route_info = payload.get("routeInfo")
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

			initial_result: PrerenderResult = {
				"views": {},
				"directives": {
					"headers": {"X-Pulse-Render-Id": render_id},
					"socketio": {"auth": {"render_id": render_id}, "headers": {}},
				},
			}

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

			result = initial_result.copy()

			with PulseContext.update(render=render):
				for p in paths:
					try:
						res = self.middleware.prerender_route(
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

			# Call top-level batch prerender middleware to modify final result
			def _return_result() -> PrerenderResult:
				return result

			final_result = self.middleware.prerender(
				payload=payload,
				result=result,
				request=PulseRequest.from_fastapi(request),
				session=session.data,
				next=_return_result,
			)

			resp = JSONResponse(serialize(final_result))
			session.handle_response(resp)
			return resp

		@self.fastapi.post(f"{prefix}/forms/{{render_id}}/{{form_id}}")
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

		@self.sio.event
		async def connect(  # pyright: ignore[reportUnusedFunction]
			sid: str, environ: dict[str, Any], auth: dict[str, str] | None
		):
			# Expect renderId during websocket auth and require a valid user session
			rid = auth.get("render_id") if auth else None

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
		def disconnect(sid: str):  # pyright: ignore[reportUnusedFunction]
			rid = self._socket_to_render.pop(sid, None)
			if rid is not None:
				# Close the RenderSession entirely to avoid lingering effects/tasks
				self.close_render(rid)

		@self.sio.event
		def message(sid: str, data: Serialized):  # pyright: ignore[reportUnusedFunction]
			rid = self._socket_to_render.get(sid)
			if not rid:
				return
			render = self.render_sessions.get(rid)
			if render is None:
				return
			# Use renderId mapping to user session
			session = self.user_sessions[self._render_to_user[rid]]
			# Make sure to properly deserialize the message contents
			msg = cast(ClientMessage, deserialize(data))
			try:
				if msg["type"] == "channel_message":
					self._handle_channel_message(render, session, msg)
				else:
					self._handle_pulse_message(render, session, msg)
			except Exception as e:
				path = msg.get("path", "")
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
				render.channels.remove_route(msg["path"])
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
			render.channels.handle_client_response(msg)
		else:
			channel_id = str(msg.get("channel", ""))
			msg = cast(ClientChannelRequestMessage, msg)

			def _next() -> Ok[Any]:
				return Ok(
					render.channels.handle_client_event(
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
		self, rid: str, session: UserSession, *, client_address: str | None = None
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
		render = self.render_sessions.pop(rid, None)
		if not render:
			return
		sid = self._render_to_user.pop(rid)
		session = self.user_sessions[sid]
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

	async def close(self):
		"""
		Close the app and clean up all sessions.
		This method is called automatically during shutdown.
		"""

		# Close all render sessions
		for rid in list(self.render_sessions.keys()):
			self.close_render(rid)

		# Close all user sessions
		for sid in list(self.user_sessions.keys()):
			self.close_session(sid)

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
		create_task(render.call_api("/set-cookies", method="GET"))
		sess.scheduled_cookie_refresh = True


def add_react_components(
	routes: Sequence[Route | Layout],
	components: list[ReactComponent[Any]],
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
