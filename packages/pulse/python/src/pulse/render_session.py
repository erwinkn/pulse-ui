import asyncio
import logging
import traceback
import uuid
from asyncio import iscoroutine
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, overload

from pulse.context import PulseContext
from pulse.helpers import create_future_on_loop, create_task
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import (
	ServerApiCallMessage,
	ServerErrorPhase,
	ServerInitMessage,
	ServerJsExecMessage,
	ServerMessage,
	ServerNavigateToMessage,
	ServerUpdateMessage,
)
from pulse.queries.store import QueryStore
from pulse.reactive import Effect, flush_effects
from pulse.renderer import RenderTree
from pulse.routing import (
	Layout,
	Route,
	RouteContext,
	RouteInfo,
	RouteTree,
	ensure_absolute_path,
)
from pulse.state import State
from pulse.transpiler.id import next_id
from pulse.transpiler.nodes import Element, Expr, emit

if TYPE_CHECKING:
	from pulse.channel import ChannelsManager
	from pulse.form import FormRegistry

logger = logging.getLogger(__file__)


class JsExecError(Exception):
	"""Raised when client-side JS execution fails."""


# Module-level convenience wrapper
@overload
def run_js(expr: Expr | str, *, result: Literal[True]) -> asyncio.Future[Any]: ...


@overload
def run_js(expr: Expr | str, *, result: Literal[False] = ...) -> None: ...


def run_js(expr: Expr | str, *, result: bool = False) -> asyncio.Future[Any] | None:
	"""Execute JavaScript on the client. Convenience wrapper for RenderSession.run_js()."""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("run_js() can only be called during callback execution")
	return ctx.render.run_js(expr, result=result)


class RouteMount:
	render: "RenderSession"
	route: RouteContext
	tree: RenderTree
	effect: Effect | None
	_pulse_ctx: PulseContext | None
	element: Element
	rendered: bool

	def __init__(
		self, render: "RenderSession", route: Route | Layout, route_info: RouteInfo
	) -> None:
		self.render = render
		self.route = RouteContext(route_info, route)
		self.effect = None
		self._pulse_ctx = None
		self.element = route.render()
		self.tree = RenderTree(self.element)
		self.rendered = False


class RenderSession:
	id: str
	routes: RouteTree
	channels: "ChannelsManager"
	forms: "FormRegistry"
	query_store: QueryStore
	route_mounts: dict[str, RouteMount]
	connected: bool
	_server_address: str | None
	_client_address: str | None
	_send_message: Callable[[ServerMessage], Any] | None
	_pending_api: dict[str, asyncio.Future[dict[str, Any]]]
	_pending_js_results: dict[str, asyncio.Future[Any]]
	_global_states: dict[str, State]

	def __init__(
		self,
		id: str,
		routes: RouteTree,
		*,
		server_address: str | None = None,
		client_address: str | None = None,
	) -> None:
		from pulse.channel import ChannelsManager
		from pulse.form import FormRegistry

		self.id = id
		self.routes = routes
		self.route_mounts = {}
		# Base server address for building absolute API URLs (e.g., http://localhost:8000)
		self._server_address = server_address
		# Best-effort client address, captured at prerender or socket connect time
		self._client_address = client_address
		self._send_message = None
		# Registry of per-session global singletons (created via ps.global_state without id)
		self._global_states = {}
		self.query_store = QueryStore()
		# Connection state
		self.connected = False
		self.channels = ChannelsManager(self)
		self.forms = FormRegistry(self)
		self._pending_api = {}
		# Pending JS execution results (for awaiting run_js().result())
		self._pending_js_results = {}

	@property
	def server_address(self) -> str:
		if self._server_address is None:
			raise RuntimeError("Server address not set")
		return self._server_address

	@property
	def client_address(self) -> str:
		if self._client_address is None:
			raise RuntimeError("Client address not set")
		return self._client_address

	# Effect error handler (batch-level) to surface runtime errors
	def _on_effect_error(self, effect: Any, exc: Exception):
		# TODO: wirte into effects created within a Render

		# We don't want to couple effects to routing; broadcast to all active paths
		details = {"effect": getattr(effect, "name", "<unnamed>")}
		for path in list(self.route_mounts.keys()):
			self.report_error(path, "effect", exc, details)

	def connect(self, send_message: Callable[[ServerMessage], Any]):
		self._send_message = send_message
		self.connected = True
		# Don't flush buffer or resume effects here - mount() handles reconnection
		# by resetting mount.rendered and resuming effects to send fresh vdom_init

	def disconnect(self):
		"""Called when client disconnects - pause render effects."""
		self._send_message = None
		self.connected = False
		for mount in self.route_mounts.values():
			if mount.effect:
				mount.effect.pause()

	def send(self, message: ServerMessage):
		# If a sender is available (connected or during prerender capture), send immediately.
		# Otherwise, drop the message - we'll send full VDOM state on reconnection.
		if self._send_message:
			self._send_message(message)

	def report_error(
		self,
		path: str,
		phase: ServerErrorPhase,
		exc: BaseException,
		details: dict[str, Any] | None = None,
	):
		self.send(
			{
				"type": "server_error",
				"path": path,
				"error": {
					"message": str(exc),
					"stack": traceback.format_exc(),
					"phase": phase,
					"details": details or {},
				},
			}
		)
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
			self.unmount(path)
		self.route_mounts.clear()
		# Dispose per-session global singletons if they expose dispose()
		for value in self._global_states.values():
			value.dispose()
		self._global_states.clear()
		# Dispose all channels for this render session
		for channel_id in list(self.channels._channels.keys()):  # pyright: ignore[reportPrivateUsage]
			channel = self.channels._channels.get(channel_id)  # pyright: ignore[reportPrivateUsage]
			if channel:
				channel.closed = True
				self.channels.dispose_channel(channel, reason="render.close")
		# Cancel pending API calls
		for fut in self._pending_api.values():
			if not fut.done():
				fut.cancel()
		self._pending_api.clear()
		# Cancel pending JS execution results
		for fut in self._pending_js_results.values():
			if not fut.done():
				fut.cancel()
		self._pending_js_results.clear()
		# The effect will be garbage collected, and with it the dependencies
		self._send_message = None
		self.connected = False

	def execute_callback(self, path: str, key: str, args: list[Any] | tuple[Any, ...]):
		mount = self.route_mounts[path]
		cb = mount.tree.callbacks[key]

		def report(e: BaseException, is_async: bool = False):
			self.report_error(path, "callback", e, {"callback": key, "async": is_async})

		try:
			with PulseContext.update(render=self, route=mount.route):
				res = cb.fn(*args[: cb.n_args])
				if iscoroutine(res):
					create_task(
						res, on_done=lambda t: (e := t.exception()) and report(e, True)
					)
		except Exception as e:
			report(e)

	async def call_api(
		self,
		url_or_path: str,
		*,
		method: str = "POST",
		headers: dict[str, str] | None = None,
		body: Any | None = None,
		credentials: str = "include",
		timeout: float = 30.0,
	) -> dict[str, Any]:
		"""Request the client to perform a fetch and await the result.

		Accepts either an absolute URL (http/https) or a relative path. When a
		relative path is provided, it is resolved against this session's
		server_address.

		Args:
			timeout: Maximum seconds to wait for response (default 30s).
			         Raises asyncio.TimeoutError if exceeded.
		"""
		# Resolve to absolute URL if a relative path is passed
		if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
			url = url_or_path
		else:
			base = self.server_address
			if not base:
				raise RuntimeError(
					"Server address unavailable. Ensure App.run_codegen/asgi_factory set server_address."
				)
			path = url_or_path if url_or_path.startswith("/") else "/" + url_or_path
			url = f"{base}{path}"
		corr_id = uuid.uuid4().hex
		fut = create_future_on_loop()
		self._pending_api[corr_id] = fut
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
		try:
			result = await asyncio.wait_for(fut, timeout=timeout)
		except asyncio.TimeoutError:
			self._pending_api.pop(corr_id, None)
			raise
		return result

	def handle_api_result(self, data: dict[str, Any]):
		id_ = data.get("id")
		if id_ is None:
			return
		id_ = str(id_)
		fut = self._pending_api.pop(id_, None)
		if fut and not fut.done():
			fut.set_result(
				{
					"ok": data.get("ok", False),
					"status": data.get("status", 0),
					"headers": data.get("headers", {}),
					"body": data.get("body"),
				}
			)

	# ---- JS Execution ----
	@overload
	def run_js(
		self, expr: Expr | str, *, result: Literal[True], timeout: float = ...
	) -> asyncio.Future[object]: ...

	@overload
	def run_js(
		self,
		expr: Expr | str,
		*,
		result: Literal[False] = ...,
		timeout: float = ...,
	) -> None: ...

	def run_js(
		self, expr: Expr | str, *, result: bool = False, timeout: float = 10.0
	) -> asyncio.Future[object] | None:
		"""Execute JavaScript on the client.

		Args:
			expr: A Expr (e.g. from calling a @javascript function) or raw JS string.
			result: If True, returns a Future that resolves with the JS return value.
			        If False (default), returns None (fire-and-forget).
			timeout: Maximum seconds to wait for result (default 10s, only applies when
			         result=True). Future raises asyncio.TimeoutError if exceeded.

		Returns:
			None if result=False, otherwise a Future resolving to the JS result.

		Example - Fire and forget:
			@javascript
			def focus_element(selector: str):
				document.querySelector(selector).focus()

			def on_save():
				save_data()
				run_js(focus_element("#next-input"))

		Example - Await result:
			@javascript
			def get_scroll_position():
				return {"x": window.scrollX, "y": window.scrollY}

			async def on_click():
				pos = await run_js(get_scroll_position(), result=True)
				print(pos["x"], pos["y"])

		Example - Raw JS string:
			def on_click():
				run_js("console.log('Hello from Python!')")
		"""
		ctx = PulseContext.get()
		exec_id = next_id()

		if isinstance(expr, str):
			code = expr
		else:
			code = emit(expr)

		# Get route pattern path (e.g., "/users/:id") not pathname (e.g., "/users/123")
		# This must match the path used to key views on the client side
		path = ctx.route.pulse_route.unique_path() if ctx.route else "/"

		self.send(
			ServerJsExecMessage(
				type="js_exec",
				path=path,
				id=exec_id,
				code=code,
			)
		)

		if result:
			loop = asyncio.get_running_loop()
			future: asyncio.Future[object] = loop.create_future()
			self._pending_js_results[exec_id] = future

			# Schedule auto-timeout
			def _on_timeout() -> None:
				self._pending_js_results.pop(exec_id, None)
				if not future.done():
					future.set_exception(asyncio.TimeoutError())

			loop.call_later(timeout, _on_timeout)

			return future

		return None

	def handle_js_result(self, data: dict[str, Any]) -> None:
		"""Handle js_result message from client."""
		exec_id = data.get("id")
		if exec_id is None:
			return
		exec_id = str(exec_id)
		fut = self._pending_js_results.pop(exec_id, None)
		if fut is None or fut.done():
			return
		error = data.get("error")
		if error is not None:
			fut.set_exception(JsExecError(error))
		else:
			fut.set_result(data.get("result"))

	def create_route_mount(self, path: str, route_info: RouteInfo | None = None):
		route = self.routes.find(path)
		mount = RouteMount(self, route, route_info or route.default_route_info())
		self.route_mounts[path] = mount
		return mount

	def prerender_mount_capture(
		self, path: str, route_info: RouteInfo | None = None
	) -> ServerInitMessage | ServerNavigateToMessage:
		"""
		Mount the route and run the render effect immediately, capturing the
		initial message instead of sending over a socket.

		Returns a dict:
		  { "type": "vdom_init", "vdom": VDOM } or
		  { "type": "navigate_to", "path": str, "replace": bool }
		"""
		# If already mounted (e.g., repeated prerender), do nothing special.
		if path in self.route_mounts:
			# Run a diff and synthesize an update; however, for prerender we
			# expect initial mount. Return current tree as a full VDOM.
			mount = self.get_route_mount(path)
			with PulseContext.update(route=mount.route):
				vdom = mount.tree.render()
				normalized_root = getattr(mount.tree, "_normalized", None)
				if normalized_root is not None:
					mount.element = normalized_root
				mount.rendered = True
				return ServerInitMessage(type="vdom_init", path=path, vdom=vdom)

		captured: ServerInitMessage | ServerNavigateToMessage | None = None

		def _capture(msg: ServerMessage):
			nonlocal captured
			# Only capture the first relevant message for this path
			if captured is not None:
				return
			if msg["type"] == "vdom_init" and msg["path"] == path:
				captured = ServerInitMessage(
					type="vdom_init", path=path, vdom=msg.get("vdom")
				)
			elif msg["type"] == "navigate_to":
				captured = ServerNavigateToMessage(
					type="navigate_to",
					path=msg["path"],
					replace=msg["replace"],
					hard=msg.get("hard", False),
				)

		prev_sender = self._send_message
		try:
			self._send_message = _capture
			# Reuse normal mount flow which creates and runs the effect
			self.mount(path, route_info or self.routes.find(path).default_route_info())
			# Flush any scheduled effects to stabilize output
			self.flush()
		finally:
			self._send_message = prev_sender

		# Fallback: if nothing captured (shouldn't happen), return full VDOM
		if captured is None:
			mount = self.get_route_mount(path)
			with PulseContext.update(route=mount.route):
				vdom = mount.tree.render()
				normalized_root = getattr(mount.tree, "_normalized", None)
				if normalized_root is not None:
					mount.element = normalized_root
				mount.rendered = True
			return ServerInitMessage(type="vdom_init", path=path, vdom=vdom)

		return captured

	def get_route_mount(
		self,
		path: str,
	):
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			raise ValueError(f"No active route for '{path}'")
		return mount

	# ---- Session-local global state registry ----
	def get_global_state(self, key: str, factory: Callable[[], Any]) -> Any:
		"""Return a per-session singleton for the provided key."""
		inst = self._global_states.get(key)
		if inst is None:
			inst = factory()
			self._global_states[key] = inst
		return inst

	def render(self, path: str, route_info: RouteInfo | None = None):
		mount = self.create_route_mount(path, route_info)
		with PulseContext.update(route=mount.route):
			vdom = mount.tree.render()
			normalized_root = getattr(mount.tree, "_normalized", None)
			if normalized_root is not None:
				mount.element = normalized_root
			mount.rendered = True
			return vdom

	def rerender(self, path: str):
		mount = self.get_route_mount(path)
		with PulseContext.update(route=mount.route):
			ops = mount.tree.diff(mount.element)
			normalized_root = getattr(mount.tree, "_normalized", None)
			if normalized_root is not None:
				mount.element = normalized_root
			return ops

	def mount(self, path: str, route_info: RouteInfo):
		if path in self.route_mounts:
			# Route already mounted - this is a reconnection case.
			# Reset rendered flag so effect sends vdom_init, update route info,
			# and resume the paused effect.
			mount = self.route_mounts[path]
			mount.rendered = False
			mount.route.update(route_info)
			if mount.effect and mount.effect.paused:
				mount.effect.resume()
			return

		mount = self.create_route_mount(path, route_info)
		# Get current context + add RouteContext. Save it to be able to mount it
		# whenever the render effect reruns.
		ctx = PulseContext.get()
		session = ctx.session

		def _render_effect():
			# Always ensure both render and route are present in context
			with PulseContext.update(session=session, render=self, route=mount.route):
				try:
					if not mount.rendered:
						vdom = mount.tree.render()
						normalized_root = getattr(mount.tree, "_normalized", None)
						if normalized_root is not None:
							mount.element = normalized_root
						mount.rendered = True
						self.send(
							ServerInitMessage(type="vdom_init", path=path, vdom=vdom)
						)
					else:
						ops = mount.tree.diff(mount.element)
						normalized_root = getattr(mount.tree, "_normalized", None)
						if normalized_root is not None:
							mount.element = normalized_root
						if ops:
							self.send(
								ServerUpdateMessage(
									type="vdom_update", path=path, ops=ops
								)
							)
				except RedirectInterrupt as r:
					# Prefer client-side navigation over emitting VDOM operations
					self.send(
						ServerNavigateToMessage(
							type="navigate_to",
							path=r.path,
							replace=r.replace,
							hard=False,
						)
					)
				except NotFoundInterrupt:
					# Use app-configured not-found path; fallback to '/404'
					self.send(
						ServerNavigateToMessage(
							type="navigate_to",
							path=ctx.app.not_found,
							replace=True,
							hard=False,
						)
					)

		mount.effect = Effect(
			_render_effect,
			immediate=True,
			name=f"{path}:render",
			on_error=lambda e: self.report_error(path, "render", e),
		)

	def flush(self):
		# Ensure effects (including route render effects) run with this session
		# bound on the PulseContext so hooks like ps.global_state work
		with PulseContext.update(render=self):
			flush_effects()

	def navigate(self, path: str, route_info: RouteInfo):
		# Route is already mounted, we can just update the routing state
		try:
			mount = self.get_route_mount(path)
			mount.route.update(route_info)
		except Exception as e:
			self.report_error(path, "navigate", e)

	def unmount(self, path: str):
		if path not in self.route_mounts:
			return
		try:
			mount = self.route_mounts.pop(path)
			mount.tree.unmount()
			if mount.effect:
				mount.effect.dispose()
		except Exception as e:
			self.report_error(path, "unmount", e)
