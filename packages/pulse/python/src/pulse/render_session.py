import asyncio
import logging
import traceback
import uuid
from asyncio import iscoroutine
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, overload

from pulse.context import (
	PulseContext,
	UserContextSnapshot,
	get_user_context_snapshot,
	restore_user_context,
)
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
from pulse.transpiler.nodes import Expr

if TYPE_CHECKING:
	from pulse.channel import ChannelsManager
	from pulse.form import FormRegistry

logger = logging.getLogger(__file__)


class JsExecError(Exception):
	"""Raised when client-side JS execution fails."""


# Module-level convenience wrapper
@overload
def run_js(expr: Expr, *, result: Literal[True]) -> asyncio.Future[Any]: ...


@overload
def run_js(expr: Expr, *, result: Literal[False] = ...) -> None: ...


def run_js(expr: Expr, *, result: bool = False) -> asyncio.Future[Any] | None:
	"""Execute JavaScript on the client. Convenience wrapper for RenderSession.run_js()."""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("run_js() can only be called during callback execution")
	return ctx.render.run_js(expr, result=result)


MountState = Literal["pending", "active", "idle"]


class RouteMount:
	render: "RenderSession"
	route: RouteContext
	tree: RenderTree | None
	effect: Effect | None
	_pulse_ctx: PulseContext | None
	initialized: bool
	state: MountState
	queue: list[ServerMessage] | None
	queue_timeout: asyncio.TimerHandle | None
	user_context_snapshot: UserContextSnapshot

	def __init__(
		self, render: "RenderSession", route: Route | Layout, route_info: RouteInfo
	) -> None:
		self.render = render
		self.route = RouteContext(route_info, route)
		self.effect = None
		self._pulse_ctx = None
		self.tree = None
		self.initialized = False
		self.state = "pending"
		self.queue = None
		self.queue_timeout = None
		# Capture user context snapshot for inheritance (set during prerender/attach)
		self.user_context_snapshot = ()


class RenderSession:
	id: str
	routes: RouteTree
	channels: "ChannelsManager"
	forms: "FormRegistry"
	query_store: QueryStore
	route_mounts: dict[str, RouteMount]
	connected: bool
	prerender_queue_timeout: float
	disconnect_queue_timeout: float
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
		prerender_queue_timeout: float = 5.0,
		disconnect_queue_timeout: float = 2.0,
	) -> None:
		from pulse.channel import ChannelsManager
		from pulse.form import FormRegistry

		self.id = id
		self.routes = routes
		self.route_mounts = {}
		self._server_address = server_address
		self._client_address = client_address
		self._send_message = None
		self._global_states = {}
		self.query_store = QueryStore()
		self.connected = False
		self.channels = ChannelsManager(self)
		self.forms = FormRegistry(self)
		self._pending_api = {}
		self._pending_js_results = {}
		self.prerender_queue_timeout = prerender_queue_timeout
		self.disconnect_queue_timeout = disconnect_queue_timeout

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

	def _on_effect_error(self, effect: Any, exc: Exception):
		details = {"effect": getattr(effect, "name", "<unnamed>")}
		for path in list(self.route_mounts.keys()):
			self.report_error(path, "effect", exc, details)

	# ---- Connection lifecycle ----

	def connect(self, send_message: Callable[[ServerMessage], Any]):
		"""WebSocket connected. Set sender, don't auto-flush (attach does that)."""
		self._send_message = send_message
		self.connected = True

	def disconnect(self):
		"""WebSocket disconnected. Start queuing briefly before pausing."""
		self._send_message = None
		self.connected = False

		for path, mount in self.route_mounts.items():
			if mount.state == "active":
				mount.state = "pending"
				mount.queue = []
				mount.queue_timeout = self._schedule_timeout(
					self.disconnect_queue_timeout,
					lambda p=path: self._transition_to_idle(p),
				)

	# ---- Message routing ----

	def send(self, message: ServerMessage):
		"""Route message based on mount state."""
		# Global messages (not path-specific) go directly if connected
		path = message.get("path")
		if path is None:
			if self._send_message:
				self._send_message(message)
			return

		# Normalize path for lookup
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			# Unknown path - send directly if connected (for js_exec, etc.)
			if self._send_message:
				self._send_message(message)
			return

		if mount.state == "pending" and mount.queue is not None:
			mount.queue.append(message)
		elif mount.state == "active" and self._send_message:
			self._send_message(message)
		# idle: drop (effect should be paused anyway)

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

	# ---- State transitions ----

	def _schedule_timeout(
		self, delay: float, callback: Callable[[], None]
	) -> asyncio.TimerHandle:
		loop = asyncio.get_event_loop()
		return loop.call_later(delay, callback)

	def _cancel_queue_timeout(self, mount: RouteMount):
		if mount.queue_timeout is not None:
			mount.queue_timeout.cancel()
			mount.queue_timeout = None

	def _transition_to_idle(self, path: str):
		mount = self.route_mounts.get(path)
		if mount is None or mount.state != "pending":
			return

		mount.state = "idle"
		mount.queue = None
		mount.queue_timeout = None
		if mount.effect:
			mount.effect.pause()

	# ---- Prerendering ----

	def _build_route_hierarchy(self, path: str) -> list[Route | Layout]:
		"""Build the list of routes/layouts from root to the matched route."""
		matched_route = self.routes.find(path)
		hierarchy: list[Route | Layout] = []
		current: Route | Layout | None = matched_route

		# Walk up to root, collecting all ancestors
		while current is not None:
			hierarchy.insert(0, current)
			current = current.parent  # type: ignore

		return hierarchy

	def _get_unified_tree_element(self, hierarchy: list[Route | Layout]) -> Any:
		"""Get the root element for rendering the full hierarchy as one tree.

		For F-0034, this returns the root of the hierarchy (first layout or route).
		The element will render with Outlets as placeholders.
		For F-0035, Outlets will be replaced with child route content.
		"""
		if not hierarchy:
			raise ValueError("Hierarchy cannot be empty")

		# Return the root element (first in hierarchy)
		# If there are layouts, this renders the root layout with empty Outlets
		# If there are no layouts, this renders the matched route directly
		return hierarchy[0].render()

	def prerender(
		self, path: str, route_info: RouteInfo | None = None
	) -> ServerInitMessage | ServerNavigateToMessage:
		"""
		Synchronous render for SSR. Returns vdom_init or navigate_to message.
		- First call: creates RouteMount for the matched route, starts queue
		- Subsequent calls: re-renders and returns fresh VDOM
		- Renders unified VDOM tree (single tree from root layouts to matched route)

		Child routes inherit context from parent routes via context snapshots.
		"""
		path = ensure_absolute_path(path)
		matched_route = self.routes.find(path)
		is_new = path not in self.route_mounts

		info = route_info or matched_route.default_route_info()

		# Ensure all ancestors in the route hierarchy have mounts
		hierarchy = self._build_route_hierarchy(path)
		for ancestor in hierarchy[:-1]:  # All except the final matched route
			ancestor_path = ancestor.unique_path()
			if ancestor_path not in self.route_mounts:
				ancestor_mount = RouteMount(
					self, ancestor, ancestor.default_route_info()
				)  # type: ignore
				ancestor_mount.state = "pending"
				ancestor_mount.queue = []
				self.route_mounts[ancestor_path] = ancestor_mount

		# Get or create mount for the matched route
		if is_new:
			mount = RouteMount(self, matched_route, info)
			mount.state = "pending"
			mount.queue = []
			self.route_mounts[path] = mount
		else:
			mount = self.route_mounts[path]
			mount.route.update(info)

		# Get parent context snapshot for inheritance
		parent_context = self.get_parent_context_snapshot(matched_route)

		with PulseContext.update(render=self, route=mount.route):
			# Restore parent context so child can inherit
			with restore_user_context(parent_context):
				try:
					# Render unified VDOM tree starting from root of hierarchy
					root_element = self._get_unified_tree_element(hierarchy)
					root_tree = RenderTree(root_element)
					vdom = root_tree.render()
					# Store the tree on the mount for later re-renders
					mount.tree = root_tree
					# Capture context snapshot after render (includes any pulse_context() used)
					mount.user_context_snapshot = get_user_context_snapshot()
					if is_new:
						mount.initialized = True
				except RedirectInterrupt as r:
					del self.route_mounts[path]
					return ServerNavigateToMessage(
						type="navigate_to", path=r.path, replace=r.replace, hard=False
					)
				except NotFoundInterrupt:
					del self.route_mounts[path]
					ctx = PulseContext.get()
					return ServerNavigateToMessage(
						type="navigate_to",
						path=ctx.app.not_found,
						replace=True,
						hard=False,
					)

		if is_new:
			self._create_render_effect(mount, path)
			mount.queue_timeout = self._schedule_timeout(
				self.prerender_queue_timeout,
				lambda: self._transition_to_idle(path),
			)

		return ServerInitMessage(type="vdom_init", path=path, vdom=vdom)

	# ---- Client lifecycle ----

	def attach(self, path: str, route_info: RouteInfo):
		"""
		Client ready to receive updates for path.
		- PENDING: flush queue, transition to ACTIVE
		- IDLE: fresh render, transition to ACTIVE
		- ACTIVE: update route_info
		- No mount: create fresh
		"""
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)

		if mount is None:
			# No prerender, create fresh
			route = self.routes.find(path)
			mount = RouteMount(self, route, route_info)
			mount.state = "active"
			self.route_mounts[path] = mount
			self._create_render_effect(mount, path)
			return

		if mount.state == "pending":
			# Flush queue, go active
			self._cancel_queue_timeout(mount)
			if mount.queue:
				for msg in mount.queue:
					if self._send_message:
						self._send_message(msg)
			mount.queue = None
			mount.state = "active"
			mount.route.update(route_info)

		elif mount.state == "idle":
			# Need fresh render
			mount.initialized = False
			mount.state = "active"
			mount.route.update(route_info)
			if mount.effect:
				mount.effect.resume()

		elif mount.state == "active":
			# Already active, just update route
			mount.route.update(route_info)

	def update_route(self, path: str, route_info: RouteInfo):
		"""Update routing state (query params, etc.) for attached path."""
		path = ensure_absolute_path(path)
		try:
			mount = self.get_route_mount(path)
			mount.route.update(route_info)
		except Exception as e:
			self.report_error(path, "navigate", e)

	def detach(self, path: str):
		"""Client no longer wants updates. Dispose Effect, remove mount."""
		path = ensure_absolute_path(path)
		if path not in self.route_mounts:
			return
		try:
			mount = self.route_mounts.pop(path)
			self._cancel_queue_timeout(mount)
			if mount.tree is not None:
				mount.tree.unmount()
			if mount.effect:
				mount.effect.dispose()
		except Exception as e:
			self.report_error(path, "unmount", e)

	# ---- Effect creation ----

	def _create_render_effect(self, mount: RouteMount, path: str):
		ctx = PulseContext.get()
		session = ctx.session
		# Capture parent context at effect creation time
		parent_context = self.get_parent_context_snapshot(mount.route.pulse_route)

		def _render_effect():
			with PulseContext.update(session=session, render=self, route=mount.route):
				# Restore parent context for inheritance
				with restore_user_context(parent_context):
					try:
						if not mount.initialized:
							# Initialize tree on first render if not already set
							if mount.tree is None:
								hierarchy = self._build_route_hierarchy(path)
								root_element = self._get_unified_tree_element(hierarchy)
								mount.tree = RenderTree(root_element)
							vdom = mount.tree.render()
							# Update snapshot after render
							mount.user_context_snapshot = get_user_context_snapshot()
							mount.initialized = True
							self.send(
								ServerInitMessage(
									type="vdom_init", path=path, vdom=vdom
								)
							)
						else:
							# Tree should exist for re-renders
							if mount.tree is not None:
								ops = mount.tree.rerender()
								# Update snapshot after re-render
								mount.user_context_snapshot = (
									get_user_context_snapshot()
								)
								if ops:
									self.send(
										ServerUpdateMessage(
											type="vdom_update", path=path, ops=ops
										)
									)
					except RedirectInterrupt as r:
						self.send(
							ServerNavigateToMessage(
								type="navigate_to",
								path=r.path,
								replace=r.replace,
								hard=False,
							)
						)
					except NotFoundInterrupt:
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

	# ---- Helpers ----

	def close(self):
		self.forms.dispose()
		for path in list(self.route_mounts.keys()):
			self.detach(path)
		self.route_mounts.clear()
		for value in self._global_states.values():
			value.dispose()
		self._global_states.clear()
		for channel_id in list(self.channels._channels.keys()):  # pyright: ignore[reportPrivateUsage]
			channel = self.channels._channels.get(channel_id)  # pyright: ignore[reportPrivateUsage]
			if channel:
				channel.closed = True
				self.channels.dispose_channel(channel, reason="render.close")
		for fut in self._pending_api.values():
			if not fut.done():
				fut.cancel()
		self._pending_api.clear()
		for fut in self._pending_js_results.values():
			if not fut.done():
				fut.cancel()
		self._pending_js_results.clear()
		self._send_message = None
		self.connected = False

	def get_route_mount(self, path: str) -> RouteMount:
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			raise ValueError(f"No active route for '{path}'")
		return mount

	def get_parent_context_snapshot(self, route: Route | Layout) -> UserContextSnapshot:
		"""Get the user context snapshot from the parent route's mount.

		Returns empty tuple if no parent or parent mount not found.
		Child routes inherit context from their parent layouts/routes.
		"""
		parent = route.parent
		if parent is None:
			return ()
		parent_path = parent.unique_path()
		parent_mount = self.route_mounts.get(parent_path)
		if parent_mount is None:
			return ()
		return parent_mount.user_context_snapshot

	def get_global_state(self, key: str, factory: Callable[[], Any]) -> Any:
		"""Return a per-session singleton for the provided key."""
		inst = self._global_states.get(key)
		if inst is None:
			inst = factory()
			self._global_states[key] = inst
		return inst

	def flush(self):
		with PulseContext.update(render=self):
			flush_effects()

	def execute_callback(self, path: str, key: str, args: list[Any] | tuple[Any, ...]):
		mount = self.route_mounts[path]
		if mount.tree is None:
			self.report_error(
				path,
				"callback",
				RuntimeError(f"Mount tree not initialized for callback {key}"),
				{"callback": key},
			)
			return
		cb = mount.tree.callbacks[key]

		def report(e: BaseException, is_async: bool = False):
			self.report_error(path, "callback", e, {"callback": key, "async": is_async})

		try:
			with PulseContext.update(render=self, route=mount.route):
				# Restore user context so callbacks can access pulse_context values
				with restore_user_context(mount.user_context_snapshot):
					res = cb.fn(*args[: cb.n_args])
					if iscoroutine(res):
						create_task(
							res,
							on_done=lambda t: (e := t.exception()) and report(e, True),
						)
		except Exception as e:
			report(e)

	# ---- API calls ----

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
		"""Request the client to perform a fetch and await the result."""
		if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
			url = url_or_path
		else:
			base = self.server_address
			if not base:
				raise RuntimeError(
					"Server address unavailable. Ensure App.run_codegen/asgi_factory set server_address."
				)
			api_path = url_or_path if url_or_path.startswith("/") else "/" + url_or_path
			url = f"{base}{api_path}"
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
		self, expr: Expr, *, result: Literal[True], timeout: float = ...
	) -> asyncio.Future[object]: ...

	@overload
	def run_js(
		self,
		expr: Expr,
		*,
		result: Literal[False] = ...,
		timeout: float = ...,
	) -> None: ...

	def run_js(
		self, expr: Expr, *, result: bool = False, timeout: float = 10.0
	) -> asyncio.Future[object] | None:
		"""Execute JavaScript on the client.

		Args:
			expr: An Expr from calling a @javascript function.
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
		"""
		ctx = PulseContext.get()
		exec_id = next_id()

		# Get route pattern path (e.g., "/users/:id") not pathname (e.g., "/users/123")
		# This must match the path used to key views on the client side
		path = ctx.route.pulse_route.unique_path() if ctx.route else "/"

		self.send(
			ServerJsExecMessage(
				type="js_exec",
				path=path,
				id=exec_id,
				expr=expr.render(),
			)
		)

		if result:
			loop = asyncio.get_running_loop()
			future: asyncio.Future[object] = loop.create_future()
			self._pending_js_results[exec_id] = future

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
