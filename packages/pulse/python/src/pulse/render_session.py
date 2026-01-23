import asyncio
import logging
import os
import traceback
import uuid
from asyncio import iscoroutine
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from pulse.context import PulseContext
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
from pulse.reactive import REACTIVE_CONTEXT, Effect, flush_effects
from pulse.renderer import RenderTree
from pulse.routing import (
	Layout,
	Route,
	RouteContext,
	RouteInfo,
	RouteTree,
	ensure_absolute_path,
)
from pulse.scheduling import (
	TaskRegistry,
	TimerHandleLike,
	TimerRegistry,
	create_future,
)
from pulse.state import State
from pulse.transpiler.id import next_id
from pulse.transpiler.nodes import Expr

if TYPE_CHECKING:
	from pulse.channel import ChannelsManager
	from pulse.forms import FormRegistry

logger = logging.getLogger(__file__)


class JsExecError(Exception):
	"""Raised when client-side JS execution fails."""


class RenderLoopError(RuntimeError):
	path: str
	renders: int
	batch_id: int

	def __init__(self, path: str, renders: int, batch_id: int) -> None:
		super().__init__(
			"Detected an infinite render loop in Pulse. "
			+ f"Render path '{path}' exceeded {renders} renders in reactive batch {batch_id}. "
			+ "This usually happens when a render or effect mutates state without a guard."
		)
		self.path = path
		self.renders = renders
		self.batch_id = batch_id


# Module-level convenience wrapper
@overload
def run_js(expr: Any, *, result: Literal[True]) -> asyncio.Future[Any]: ...


@overload
def run_js(expr: Any, *, result: Literal[False] = ...) -> None: ...


def run_js(expr: Any, *, result: bool = False) -> asyncio.Future[Any] | None:
	"""Execute JavaScript on the client. Convenience wrapper for RenderSession.run_js()."""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("run_js() can only be called during callback execution")
	return ctx.render.run_js(expr, result=result)


MountState = Literal["pending", "active", "idle", "closed"]
PendingAction = Literal["idle", "dispose"]
T_Render = TypeVar("T_Render")


class RouteMount:
	render: "RenderSession"
	path: str
	route: RouteContext
	tree: RenderTree
	effect: Effect | None
	_pulse_ctx: PulseContext | None
	initialized: bool
	state: MountState
	pending_action: PendingAction | None
	queue: list[ServerMessage] | None
	queue_timeout: TimerHandleLike | None
	render_batch_id: int
	render_batch_renders: int

	def __init__(
		self,
		render: "RenderSession",
		path: str,
		route: Route | Layout,
		route_info: RouteInfo,
	) -> None:
		self.render = render
		self.path = ensure_absolute_path(path)
		self.route = RouteContext(route_info, route)
		self.effect = None
		self._pulse_ctx = None
		self.tree = RenderTree(route.render())
		self.initialized = False
		self.state = "pending"
		self.pending_action = None
		self.queue = []
		self.queue_timeout = None
		self.render_batch_id = -1
		self.render_batch_renders = 0

	def update_route(self, route_info: RouteInfo) -> None:
		self.route.update(route_info)

	def _cancel_pending_timeout(self) -> None:
		if self.queue_timeout is not None:
			self.queue_timeout.cancel()
			self.render.discard_timer(self.queue_timeout)
			self.queue_timeout = None
		self.pending_action = None

	def _on_pending_timeout(self) -> None:
		if self.state != "pending":
			return
		action = self.pending_action
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print(
				"[PulseDebug][mount-timeout] render=%s path=%s action=%s state=%s"
				% (self.render.id, self.path, action, self.state)
			)
		self.pending_action = None
		if action == "dispose":
			self.render.dispose_mount(self.path, self)
			return
		self.to_idle()

	def start_pending(self, timeout: float, *, action: PendingAction = "idle") -> None:
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print(
				"[PulseDebug][mount-pending] render=%s path=%s state=%s action=%s timeout=%s"
				% (self.render.id, self.path, self.state, action, timeout)
			)
		if self.state == "pending":
			prev_action = self.pending_action
			next_action: PendingAction = (
				"dispose" if prev_action == "dispose" or action == "dispose" else "idle"
			)
			self._cancel_pending_timeout()
			self.pending_action = next_action
			self.queue_timeout = self.render.schedule_later(
				timeout, self._on_pending_timeout
			)
			return
		self._cancel_pending_timeout()
		if self.state == "idle" and self.effect:
			self.effect.resume()
		self.state = "pending"
		self.queue = []
		self.pending_action = action
		self.queue_timeout = self.render.schedule_later(
			timeout, self._on_pending_timeout
		)

	def activate(self, send_message: Callable[[ServerMessage], Any]) -> None:
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print(
				"[PulseDebug][mount-activate] render=%s path=%s state=%s queued=%s"
				% (
					self.render.id,
					self.path,
					self.state,
					0 if not self.queue else len(self.queue),
				)
			)
		if self.state != "pending":
			return
		self._cancel_pending_timeout()
		if self.queue:
			for msg in self.queue:
				send_message(msg)
		self.queue = None
		self.state = "active"

	def deliver(
		self, message: ServerMessage, send_message: Callable[[ServerMessage], Any]
	):
		if self.state == "pending":
			if self.queue is None:
				raise RuntimeError(f"Pending mount missing queue for {self.path!r}")
			self.queue.append(message)
			return
		if self.state == "active":
			send_message(message)
			return
		if self.state == "closed":
			raise RuntimeError(f"Message sent to closed mount {self.path!r}")

	def to_idle(self) -> None:
		if self.state != "pending":
			return
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print(
				"[PulseDebug][mount-idle] render=%s path=%s"
				% (self.render.id, self.path)
			)
		self.state = "idle"
		self.queue = None
		self._cancel_pending_timeout()
		if self.effect:
			self.effect.pause()

	def ensure_effect(self, *, lazy: bool = False, flush: bool = True) -> None:
		if self.effect is not None:
			if flush:
				self.effect.flush()
			return

		ctx = PulseContext.get()
		session = ctx.session

		def _render_effect():
			message = self.render.rerender(self, self.path, session=session)
			if message is not None:
				self.render.send(message)

		def _report_render_error(exc: Exception) -> None:
			details: dict[str, Any] | None = None
			if isinstance(exc, RenderLoopError):
				details = {
					"renders": exc.renders,
					"batch_id": exc.batch_id,
				}
			self.render.report_error(self.path, "render", exc, details)

		self.effect = Effect(
			_render_effect,
			immediate=False,
			name=f"{self.path}:render",
			on_error=_report_render_error,
			lazy=lazy,
		)
		if flush:
			self.effect.flush()

	def dispose(self) -> None:
		self._cancel_pending_timeout()
		self.state = "closed"
		self.queue = None
		self.tree.unmount()
		if self.effect:
			self.effect.dispose()


class RenderSession:
	id: str
	routes: RouteTree
	channels: "ChannelsManager"
	forms: "FormRegistry"
	query_store: QueryStore
	route_mounts: dict[str, RouteMount]
	connected: bool
	prerender_queue_timeout: float
	detach_queue_timeout: float
	disconnect_queue_timeout: float
	render_loop_limit: int
	_server_address: str | None
	_client_address: str | None
	_send_message: Callable[[ServerMessage], Any] | None
	_pending_api: dict[str, asyncio.Future[dict[str, Any]]]
	_pending_js_results: dict[str, asyncio.Future[Any]]
	_global_states: dict[str, State]
	_tasks: TaskRegistry
	_timers: TimerRegistry

	def __init__(
		self,
		id: str,
		routes: RouteTree,
		*,
		server_address: str | None = None,
		client_address: str | None = None,
		prerender_queue_timeout: float = 15.0,
		detach_queue_timeout: float = 15.0,
		disconnect_queue_timeout: float = 300.0,
		render_loop_limit: int = 50,
	) -> None:
		from pulse.channel import ChannelsManager
		from pulse.forms import FormRegistry

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
		self._tasks = TaskRegistry(name=f"render:{id}")
		self._timers = TimerRegistry(tasks=self._tasks, name=f"render:{id}")
		self.prerender_queue_timeout = prerender_queue_timeout
		self.detach_queue_timeout = detach_queue_timeout
		self.disconnect_queue_timeout = disconnect_queue_timeout
		self.render_loop_limit = render_loop_limit

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

	def _on_effect_error(self, effect: Effect, exc: Exception):
		details = {"effect": effect.name or "<unnamed>"}
		for path in list(self.route_mounts.keys()):
			self.report_error(path, "effect", exc, details)

	# ---- Connection lifecycle ----

	def connect(self, send_message: Callable[[ServerMessage], Any]):
		"""WebSocket connected. Set sender, don't auto-flush (attach does that)."""
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print("[PulseDebug][render-connect] render=%s" % self.id)
		self._send_message = send_message
		self.connected = True

	def disconnect(self):
		"""WebSocket disconnected. Start queuing briefly before pausing."""
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print("[PulseDebug][render-disconnect] render=%s" % self.id)
		self._send_message = None
		self.connected = False

		for mount in self.route_mounts.values():
			if mount.state == "active":
				mount.start_pending(self.disconnect_queue_timeout)

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

		if self._send_message:
			mount.deliver(message, self._send_message)
			return
		if mount.state == "pending":
			mount.deliver(message, lambda _: None)
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

	# ---- Prerendering ----

	def prerender(
		self, paths: list[str], route_info: RouteInfo | None = None
	) -> dict[str, ServerInitMessage | ServerNavigateToMessage]:
		"""
		Synchronous render for SSR. Returns per-path init or navigate_to messages.
		- Creates mounts in PENDING state and starts queue
		"""
		normalized = [ensure_absolute_path(path) for path in paths]
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print(
				"[PulseDebug][prerender] render=%s paths=%s route_info=%s"
				% (self.id, normalized, route_info)
			)

		results: dict[str, ServerInitMessage | ServerNavigateToMessage] = {}

		for path in normalized:
			route = self.routes.find(path)
			info = route_info or route.default_route_info()
			mount = self.route_mounts.get(path)
			if os.environ.get("PULSE_DEBUG_RENDER"):
				route_label = repr(route)
				print(
					"[PulseDebug][prerender] render=%s path=%s mount_state=%s route=%s"
					% (self.id, path, mount.state if mount else None, route_label)
				)

			if mount is None:
				mount = RouteMount(self, path, route, info)
				self.route_mounts[path] = mount
				mount.ensure_effect(lazy=True, flush=False)
			else:
				mount.update_route(info)
				if mount.effect is None:
					mount.ensure_effect(lazy=True, flush=False)

			if mount.state != "active" and mount.queue_timeout is None:
				mount.start_pending(self.prerender_queue_timeout)
			assert mount.effect is not None
			with mount.effect.capture_deps(update_deps=True):
				message = self.render(mount, path)

			results[path] = message
			if message["type"] == "navigate_to":
				mount.dispose()
				del self.route_mounts[path]
				continue

		return results

	# ---- Client lifecycle ----

	def attach(self, path: str, route_info: RouteInfo):
		"""
		Client ready to receive updates for path.
		- PENDING: flush queue, transition to ACTIVE
		- IDLE: request reload
		- ACTIVE: update route_info
		- No mount: request reload
		"""
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)

		if mount is None or mount.state == "idle":
			if os.environ.get("PULSE_DEBUG_RENDER"):
				print(
					"[PulseDebug][attach] render=%s path=%s mount_state=%s mounts=%s route_info=%s"
					% (
						self.id,
						path,
						mount.state if mount else None,
						{key: value.state for key, value in self.route_mounts.items()},
						route_info,
					)
				)
			# Initial render must come from prerender
			print(f"[DEBUG] Missing or idle route '{path}', reloading")
			self.send({"type": "reload"})
			return

		# Update route info for active and pending mounts
		mount.update_route(route_info)
		if mount.state == "pending" and self._send_message:
			if os.environ.get("PULSE_DEBUG_RENDER"):
				print(
					"[PulseDebug][attach] render=%s path=%s activating=true"
					% (self.id, path)
				)
			mount.activate(self._send_message)

	def update_route(self, path: str, route_info: RouteInfo):
		"""Update routing state (query params, etc.) for attached path."""
		path = ensure_absolute_path(path)
		try:
			mount = self.get_route_mount(path)
			mount.update_route(route_info)
		except Exception as e:
			self.report_error(path, "navigate", e)

	def dispose_mount(self, path: str, mount: RouteMount) -> None:
		current = self.route_mounts.get(path)
		if current is not mount:
			return
		if os.environ.get("PULSE_DEBUG_RENDER"):
			print(
				"[PulseDebug][mount-dispose] render=%s path=%s state=%s"
				% (self.id, path, mount.state)
			)
		try:
			self.route_mounts.pop(path, None)
			mount.dispose()
		except Exception as e:
			self.report_error(path, "unmount", e)

	def detach(self, path: str, *, timeout: float | None = None):
		"""Client no longer wants updates. Queue briefly, then dispose."""
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			return

		if timeout is None:
			timeout = self.detach_queue_timeout
		if timeout <= 0:
			self.dispose_mount(path, mount)
			return
		mount.start_pending(timeout, action="dispose")

	# ---- Effect creation ----

	def _check_render_loop(self, mount: RouteMount, path: str) -> None:
		batch_id = REACTIVE_CONTEXT.get().batch.flush_id
		if mount.render_batch_id == batch_id:
			mount.render_batch_renders += 1
		else:
			mount.render_batch_id = batch_id
			mount.render_batch_renders = 1
		if mount.render_batch_renders > self.render_loop_limit:
			if mount.effect:
				mount.effect.pause()
			raise RenderLoopError(path, mount.render_batch_renders, batch_id)

	def _render_with_interrupts(
		self,
		mount: RouteMount,
		path: str,
		*,
		session: Any | None = None,
		render_fn: Callable[[], T_Render],
	) -> T_Render | ServerNavigateToMessage:
		ctx = PulseContext.get()
		render_session = ctx.session if session is None else session
		with PulseContext.update(
			session=render_session, render=self, route=mount.route
		):
			try:
				self._check_render_loop(mount, path)
				return render_fn()
			except RedirectInterrupt as r:
				return ServerNavigateToMessage(
					type="navigate_to",
					path=r.path,
					replace=r.replace,
					hard=False,
				)
			except NotFoundInterrupt:
				ctx = PulseContext.get()
				return ServerNavigateToMessage(
					type="navigate_to",
					path=ctx.app.not_found,
					replace=True,
					hard=False,
				)

	def render(
		self, mount: RouteMount, path: str, *, session: Any | None = None
	) -> ServerInitMessage | ServerNavigateToMessage:
		def _render() -> ServerInitMessage:
			vdom = mount.tree.render()
			mount.initialized = True
			return ServerInitMessage(type="vdom_init", path=path, vdom=vdom)

		message = self._render_with_interrupts(
			mount, path, session=session, render_fn=_render
		)
		return message

	def rerender(
		self, mount: RouteMount, path: str, *, session: Any | None = None
	) -> ServerUpdateMessage | ServerNavigateToMessage | None:
		def _rerender() -> ServerUpdateMessage | None:
			if not mount.initialized:
				raise RuntimeError(f"rerender called before init for {path!r}")
			ops = mount.tree.rerender()
			if ops:
				return ServerUpdateMessage(type="vdom_update", path=path, ops=ops)
			return None

		return self._render_with_interrupts(
			mount, path, session=session, render_fn=_rerender
		)

	# ---- Helpers ----

	def close(self):
		self.forms.dispose()
		self._tasks.cancel_all()
		self._timers.cancel_all()
		for path in list(self.route_mounts.keys()):
			self.detach(path, timeout=0)
		self.route_mounts.clear()
		self.query_store.dispose_all()
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

	def create_task(
		self,
		coroutine: Callable[[], Any] | Awaitable[Any],
		*,
		name: str | None = None,
		on_done: Callable[[asyncio.Task[Any]], None] | None = None,
	) -> asyncio.Task[Any]:
		"""Create a tracked task tied to this render session."""
		if callable(coroutine):
			return self._tasks.create_task(coroutine(), name=name, on_done=on_done)
		return self._tasks.create_task(coroutine, name=name, on_done=on_done)

	def schedule_later(
		self, delay: float, fn: Callable[..., Any], *args: Any, **kwargs: Any
	) -> TimerHandleLike:
		"""Schedule a tracked timer tied to this render session."""
		return self._timers.later(delay, fn, *args, **kwargs)

	def discard_timer(self, handle: TimerHandleLike | None) -> None:
		"""Remove a timer handle from the session registry."""
		self._timers.discard(handle)

	def execute_callback(self, path: str, key: str, args: list[Any] | tuple[Any, ...]):
		mount = self.route_mounts[path]
		cb = mount.tree.callbacks[key]

		def report(e: BaseException, is_async: bool = False):
			self.report_error(path, "callback", e, {"callback": key, "async": is_async})

		try:
			with PulseContext.update(render=self, route=mount.route):
				res = cb.fn(*args[: cb.n_args])
				if iscoroutine(res):

					def _on_done(t: asyncio.Task[Any]) -> None:
						if t.cancelled():
							return
						try:
							exc = t.exception()
						except asyncio.CancelledError:
							return
						if exc:
							report(exc, True)

					self.create_task(res, name=f"callback:{key}", on_done=_on_done)
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
		fut = create_future()
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
		self, expr: Any, *, result: Literal[True], timeout: float = ...
	) -> asyncio.Future[object]: ...

	@overload
	def run_js(
		self,
		expr: Any,
		*,
		result: Literal[False] = ...,
		timeout: float = ...,
	) -> None: ...

	def run_js(
		self, expr: Any, *, result: bool = False, timeout: float = 10.0
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
		if not isinstance(expr, Expr):
			raise TypeError(
				f"run_js() requires an Expr (from @javascript function or pulse.js module), got {type(expr).__name__}"
			)

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

			self._timers.later(timeout, _on_timeout)

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
