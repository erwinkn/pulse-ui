import asyncio
import logging
import traceback
import uuid
from asyncio import iscoroutine
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from pulse.context import PulseContext
from pulse.helpers import create_future_on_loop, create_task
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import (
	ClientMountMessage,
	ClientNavigateMessage,
	ClientPulseMessage,
	ServerApiCallMessage,
	ServerErrorMessage,
	ServerErrorPhase,
	ServerInitMessage,
	ServerMessage,
	ServerNavigateToMessage,
	ServerUpdateMessage,
)
from pulse.reactive import Effect, flush_effects
from pulse.renderer import RenderTree
from pulse.routing import (
	Layout,
	Route,
	RouteContext,
	RouteInfo,
	RouteTree,
	normalize_path,
)
from pulse.state import State
from pulse.vdom import Element

if TYPE_CHECKING:
	from pulse.app import App
	from pulse.channel import ChannelsManager
	from pulse.form import FormRegistry
	from pulse.user_session import UserSession

logger = logging.getLogger(__file__)


class RouteMount:
	render: "RenderSession"
	route: RouteContext
	tree: RenderTree

	def __init__(
		self, render: "RenderSession", route: Route | Layout, route_info: RouteInfo
	) -> None:
		self.render = render
		self.route = RouteContext(route_info, route)
		self.effect: Effect | None = None
		self._pulse_ctx: PulseContext | None = None
		self.element: Element = route.render()
		self.tree = RenderTree(self.element)
		self.rendered: bool = False
		self.last_message: ServerMessage | None = None


class RenderSession:
	id: str
	routes: RouteTree
	channels: "ChannelsManager"
	forms: "FormRegistry"
	connected: bool
	route_mounts: dict[str, RouteMount]
	message_buffer: list[ServerMessage]
	global_states: dict[str, State]
	pending_api: dict[str, asyncio.Future[dict[str, Any]]]
	_app: "App | None"
	_client_address: str | None
	_send_message: Callable[[ServerMessage], Any] | None

	def __init__(
		self,
		id: str,
		routes: RouteTree,
		*,
		app: "App | None" = None,
		client_address: str | None = None,
	) -> None:
		from pulse.channel import ChannelsManager
		from pulse.form import FormRegistry

		self.id = id
		self.routes = routes
		self.route_mounts = {}
		self._app = app
		self._client_address = client_address
		self._send_message = None
		# Buffer messages emitted before a connection is established
		self.message_buffer = []
		self.pending_api = {}
		# Registry of per-session global singletons (created via ps.global_state without id)
		self.global_states = {}
		# Connection state
		self.connected = False
		self.channels = ChannelsManager(self)
		self.forms = FormRegistry(self)

	def _resolve_app(self) -> "App":
		try:
			ctx = PulseContext.get()
		except RuntimeError:
			ctx = None
		if ctx and ctx.app:
			return ctx.app
		if self._app is not None:
			return self._app
		raise RuntimeError("Pulse App unavailable")

	@property
	def client_address(self) -> str:
		if self._client_address is None:
			raise RuntimeError(
				"Client address unavailable. It is set during prerender or socket connect."
			)
		return self._client_address

	def set_client_address(self, address: str | None) -> None:
		self._client_address = address

	# Effect error handler (batch-level) to surface runtime errors
	def _on_effect_error(self, effect: Any, exc: Exception):
		# TODO: wire into effects created within a Render

		# We don't want to couple effects to routing; broadcast to all active paths
		details = {"effect": getattr(effect, "name", "<unnamed>")}
		for path in list(self.route_mounts.keys()):
			self.report_error(path, "effect", exc, details)

	def connect(self, send_message: Callable[[ServerMessage], Any]):
		self._send_message = send_message
		self.connected = True
		# Flush any buffered messages now that we can send
		if self.message_buffer:
			for msg in self.message_buffer:
				self._send_message(msg)
			self.message_buffer.clear()

	def send(self, message: ServerMessage):
		# If a sender is available (connected or during prerender capture), send immediately.
		# Otherwise, buffer until a connection is established.
		if self._send_message:
			self._send_message(message)
		else:
			self.message_buffer.append(message)

	def report_error(
		self,
		path: str,
		phase: ServerErrorPhase,
		exc: Exception,
		details: dict[str, Any] | None = None,
	):
		error_msg: ServerErrorMessage = {
			"type": "server_error",
			"path": path,
			"error": {
				"message": str(exc),
				"stack": traceback.format_exc(),
				"phase": phase,
				"details": details or {},
			},
		}
		self.send(error_msg)
		logger.error(
			"Error reported for path %r during %s: %s\n%s",
			path,
			phase,
			exc,
			traceback.format_exc(),
		)

	def close(self):
		self.forms.dispose()
		for path in list(self.route_mounts.keys()):
			self._handle_unmount(path)
		self.route_mounts.clear()
		# Dispose per-session global singletons if they expose dispose()
		for value in self.global_states.values():
			value.dispose()
		self.global_states.clear()
		# Dispose all channels for this render session
		for channel_id in list(self.channels._channels.keys()):  # pyright: ignore[reportPrivateUsage]
			channel = self.channels._channels.get(channel_id)  # pyright: ignore[reportPrivateUsage]
			if channel:
				channel.closed = True
				self.channels.dispose_channel(channel, reason="render.close")
		# The effect will be garbage collected, and with it the dependencies
		self._send_message = None
		# Discard any buffered messages on close
		self.message_buffer.clear()
		self.connected = False

	def execute_callback(self, path: str, key: str, args: list[Any] | tuple[Any, ...]):
		self._handle_callback(path, key, args)

	async def call_api(
		self,
		url_or_path: str,
		*,
		method: str = "POST",
		headers: dict[str, str] | None = None,
		body: Any | None = None,
		credentials: str = "include",
	) -> dict[str, Any]:
		"""Request the client to perform a fetch and await the result.

		Accepts either an absolute URL (http/https) or a relative path. When a
		relative path is provided, it is resolved against this session's
		server_address.
		"""
		# Resolve to absolute URL if a relative path is passed
		if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
			url = url_or_path
		else:
			app = self._resolve_app()
			base = app.server_address
			if not base:
				raise RuntimeError(
					"Server address unavailable. Ensure App.run_codegen/asgi_factory set server_address."
				)
			path = url_or_path if url_or_path.startswith("/") else "/" + url_or_path
			url = f"{base}{path}"
		corr_id = uuid.uuid4().hex
		fut = create_future_on_loop()
		self.pending_api[corr_id] = fut
		headers = headers or {}
		headers["x-pulse-render-id"] = self.id
		self.send(
			ServerApiCallMessage(
				type="api_call",
				id=corr_id,
				url=url,
				method=method,
				headers=headers,
				body=body,
				credentials="include" if credentials == "include" else "omit",
			)
		)
		result = await fut
		return result

	def handle_api_result(self, data: dict[str, Any]):
		self._handle_api_result(data)

	def _ensure_route_mount(
		self, path: str, route_info: RouteInfo | None = None
	) -> RouteMount:
		path = normalize_path(path)
		mount = self.route_mounts.get(path)
		if mount is None:
			route = self.routes.find(path)
			mount = RouteMount(self, route, route_info or route.default_route_info())
			self.route_mounts[path] = mount
			self._install_route_effect(path, mount)
		elif route_info is not None:
			mount.route.update(route_info)
		return mount

	def render_route(
		self,
		path: str,
		route_info: RouteInfo | None = None,
		*,
		mode: Literal["initial", "prerender"] = "initial",
	) -> ServerInitMessage | ServerNavigateToMessage:
		buffer_len = len(self.message_buffer)
		mount = self._ensure_route_mount(path, route_info)
		# Ensure any pending effects run so the result is stable
		self.flush()
		message = mount.last_message
		if mode == "prerender" and len(self.message_buffer) > buffer_len:
			del self.message_buffer[buffer_len:]
		if message is None or (
			message["type"] != "vdom_init" and message["type"] != "navigate_to"
		):
			message = self._snapshot_init(path, mount)
		return message

	def rerender_route(self, path: str) -> ServerUpdateMessage | None:
		mount = self.get_route_mount(path)
		with PulseContext.update(render=self, route=mount.route):
			message = self._render_mount(path, mount)
		if message and message["type"] == "vdom_update":
			mount.last_message = message
			return message
		return None

	def receive(self, message: ClientPulseMessage) -> None:
		match message["type"]:
			case "mount":
				self._handle_mount(message)
			case "navigate":
				self._handle_navigate(message)
			case "callback":
				self._handle_callback(
					message["path"], message["callback"], message["args"]
				)
			case "unmount":
				self._handle_unmount(message["path"])
			case "api_result":
				self._handle_api_result(dict(message))
			case _:  # pyright: ignore[reportUnnecessaryComparison]
				logger.warning("Unknown message type received: %s", message)

	def _handle_mount(self, message: "ClientMountMessage") -> None:
		self.render_route(message["path"], message["routeInfo"])

	def _handle_navigate(self, message: "ClientNavigateMessage") -> None:
		path = message["path"]
		try:
			mount = self.get_route_mount(path)
			mount.route.update(message["routeInfo"])
		except Exception as e:
			self.report_error(path, "navigate", e)

	def _handle_callback(
		self, path: str, key: str, args: list[Any] | tuple[Any, ...]
	) -> None:
		mount = self.route_mounts[path]
		try:
			cb = mount.tree.callbacks[key]
			fn, n_params = cb.fn, cb.n_args
			res = fn(*args[:n_params])
			if iscoroutine(res):

				def _on_task_done(t: asyncio.Task[Any]):
					try:
						t.result()
					except Exception as e:
						self.report_error(
							path,
							"callback",
							e,
							{"callback": key, "async": True},
						)

				create_task(res, on_done=_on_task_done)
		except Exception as e:
			self.report_error(path, "callback", e, {"callback": key})

	def _handle_unmount(self, path: str) -> None:
		if path not in self.route_mounts:
			return
		try:
			mount = self.route_mounts.pop(path)
			mount.tree.unmount()
			if mount.effect:
				mount.effect.dispose()
		except Exception as e:
			self.report_error(path, "unmount", e)
		finally:
			self.channels.remove_route(path)

	def _handle_api_result(self, data: dict[str, Any]):
		id_ = data.get("id")
		if id_ is None:
			return
		id_ = str(id_)
		fut = self.pending_api.pop(id_, None)
		if fut and not fut.done():
			fut.set_result(
				{
					"ok": data.get("ok", False),
					"status": data.get("status", 0),
					"headers": data.get("headers", {}),
					"body": data.get("body"),
				}
			)

	def _install_route_effect(self, path: str, mount: RouteMount) -> None:
		ctx = PulseContext.get()
		session = ctx.session

		def _render_effect():
			self._run_route_effect(path, mount, session)

		mount.effect = Effect(
			_render_effect,
			immediate=True,
			name=f"{path}:render",
			on_error=lambda e: self.report_error(path, "render", e),
		)

	def _run_route_effect(
		self, path: str, mount: RouteMount, session: "UserSession | None"
	) -> None:
		with PulseContext.update(session=session, render=self, route=mount.route):
			try:
				message = self._render_mount(path, mount)
			except RedirectInterrupt as r:
				message = ServerNavigateToMessage(
					type="navigate_to", path=r.path, replace=r.replace
				)
			except NotFoundInterrupt:
				app = self._resolve_app()
				message = ServerNavigateToMessage(
					type="navigate_to", path=app.not_found, replace=True
				)
			if message:
				mount.last_message = message
				self.send(message)
			else:
				mount.last_message = None

	def _render_mount(
		self, path: str, mount: RouteMount
	) -> ServerInitMessage | ServerUpdateMessage | None:
		if not mount.rendered:
			vdom = mount.tree.render()
			normalized_root = getattr(mount.tree, "_normalized", None)
			if normalized_root is not None:
				mount.element = normalized_root
			mount.rendered = True
			return ServerInitMessage(
				type="vdom_init",
				path=path,
				vdom=vdom,
				callbacks=sorted(mount.tree.callbacks.keys()),
				render_props=sorted(mount.tree.render_props),
				css_refs=sorted(mount.tree.css_refs),
			)

		ops = mount.tree.diff(mount.element)
		normalized_root = getattr(mount.tree, "_normalized", None)
		if normalized_root is not None:
			mount.element = normalized_root
		if ops:
			return ServerUpdateMessage(type="vdom_update", path=path, ops=ops)
		return None

	def _snapshot_init(
		self, path: str, mount: RouteMount
	) -> ServerInitMessage | ServerNavigateToMessage:
		with PulseContext.update(render=self, route=mount.route):
			vdom = mount.tree.render()
			normalized_root = getattr(mount.tree, "_normalized", None)
			if normalized_root is not None:
				mount.element = normalized_root
			mount.rendered = True
		message = ServerInitMessage(
			type="vdom_init",
			path=path,
			vdom=vdom,
			callbacks=sorted(mount.tree.callbacks.keys()),
			render_props=sorted(mount.tree.render_props),
			css_refs=sorted(mount.tree.css_refs),
		)
		mount.last_message = message
		return message

	def get_route_mount(self, path: str):
		path = normalize_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			raise ValueError(f"No active route for '{path}'")
		return mount

	def flush(self):
		# Ensure effects (including route render effects) run with this session
		# bound on the PulseContext so hooks like ps.global_state work
		with PulseContext.update(render=self):
			flush_effects()

	# ---- Session-local global state registry ----
	def get_global_state(self, key: str, factory: Callable[[], Any]) -> Any:
		"""Return a per-session singleton for the provided key."""
		inst = self.global_states.get(key)
		if inst is None:
			inst = factory()
			self.global_states[key] = inst
		return inst
