import asyncio
import logging
import traceback
import uuid
from asyncio import iscoroutine
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from pulse.channel import Channel
from pulse.context import PulseContext
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import (
	ClientResumeChannel,
	ClientResumeView,
	ServerApiCallMessage,
	ServerErrorMessage,
	ServerErrorPhase,
	ServerInitMessage,
	ServerJsExecMessage,
	ServerMessage,
	ServerNavigateToMessage,
	ServerResumeChannel,
	ServerResumeMessage,
	ServerResumeView,
	ServerUpdateMessage,
)
from pulse.queries.store import QueryStore
from pulse.reactive import REACTIVE_CONTEXT, Effect, Untrack, flush_effects
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
from pulse.state.state import State
from pulse.transpiler.id import next_id
from pulse.transpiler.nodes import Expr

if TYPE_CHECKING:
	from pulse.channel import ChannelsManager
	from pulse.forms import FormRegistry

logger = logging.getLogger(__file__)


class JsExecError(Exception):
	"""Raised when client-side JS execution fails."""


class RenderLoopError(RuntimeError):
	route_path: str
	renders: int
	batch_id: int

	def __init__(self, route_path: str, renders: int, batch_id: int) -> None:
		super().__init__(
			"Detected an infinite render loop in Pulse. "
			+ f"Render path '{route_path}' exceeded {renders} renders in reactive batch {batch_id}. "
			+ "This usually happens when a render or effect mutates state without a guard."
		)
		self.route_path = route_path
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


ViewState = Literal["pending", "active", "idle", "closed"]
PendingAction = Literal["idle", "dispose"]
T_Render = TypeVar("T_Render")


class View:
	"""A single rendered route or layout instance for one client.

	Each view is anchored to a unique id for its entire lifetime. Protocol
	messages between server and client are scoped to this id, so stale actors
	(callbacks, channels, navigations from disposed views) are rejected
	structurally instead of via path + generation counters.
	"""

	id: str
	render: "RenderSession"
	route_path: str
	route: RouteContext
	tree: RenderTree
	session: Any
	initialized: bool
	state: ViewState
	pending_action: PendingAction | None
	queue: list[ServerMessage] | None
	queue_timeout: TimerHandleLike | None
	render_batch_id: int
	render_batch_renders: int

	def __init__(
		self,
		render: "RenderSession",
		route_path: str,
		route: Route | Layout,
		route_info: RouteInfo,
	) -> None:
		self.id = uuid.uuid4().hex
		self.render = render
		self.route_path = ensure_absolute_path(route_path)
		self.route = RouteContext(route_info, route, render, self.route_path)
		self.session = PulseContext.get().session
		self.tree = RenderTree(route.render())
		self.tree.dispatch = self._dispatch_render
		self.initialized = False
		self.state = "pending"
		self.pending_action = None
		self.queue = []
		self.queue_timeout = None
		self.render_batch_id = -1
		self.render_batch_renders = 0

	def _dispatch_render(self, runtime: Any) -> None:
		"""Run one component re-render pass and ship its operations."""
		try:
			message = self.render.render_component_pass(self, runtime)
		except Exception as exc:
			details: dict[str, Any] | None = None
			if isinstance(exc, RenderLoopError):
				details = {"renders": exc.renders, "batch_id": exc.batch_id}
			self.render.report_error(self.id, "render", exc, details)
			return
		if message is not None:
			self.render.send(message)

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
		self.pending_action = None
		if action == "dispose":
			self.render.dispose_view(self)
			return
		self.to_idle()

	def start_pending(self, timeout: float, *, action: PendingAction = "idle") -> None:
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
		if self.state == "idle":
			self.tree.resume_effects()
		self.state = "pending"
		self.queue = []
		self.pending_action = action
		self.queue_timeout = self.render.schedule_later(
			timeout, self._on_pending_timeout
		)

	def activate(self, send_message: Callable[[ServerMessage], Any]) -> None:
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
				raise RuntimeError(
					f"Pending view missing queue for {self.route_path!r}"
				)
			self.queue.append(message)
			return
		if self.state == "active":
			send_message(message)
			return
		if self.state == "closed":
			raise RuntimeError(f"Message sent to closed view {self.route_path!r}")

	def to_idle(self) -> None:
		if self.state != "pending":
			return
		self.state = "idle"
		self.queue = None
		self._cancel_pending_timeout()
		self.tree.pause_effects()

	def dispose(self) -> None:
		self._cancel_pending_timeout()
		self.state = "closed"
		self.queue = None
		self.tree.unmount()


class RenderSession:
	id: str
	routes: RouteTree
	channels: "ChannelsManager"
	forms: "FormRegistry"
	query_store: QueryStore
	views: dict[str, View]
	connected: bool
	prerender_queue_timeout: float
	dev_strict_mode_detach_timeout: float
	disconnect_queue_timeout: float
	render_loop_limit: int
	_views_by_path: dict[str, View]
	_server_address: str | None
	_client_address: str | None
	_send_message: Callable[[ServerMessage], Any] | None
	_pending_api: dict[str, asyncio.Future[dict[str, Any]]]
	_pending_js_results: dict[str, asyncio.Future[Any]]
	_ref_channel: Channel | None
	_ref_channels_by_view: dict[str, Channel]
	_global_states: dict[str, State]
	_global_queue: list[ServerMessage]
	_tasks: TaskRegistry
	_timers: TimerRegistry

	def __init__(
		self,
		id: str,
		routes: RouteTree,
		*,
		server_address: str | None = None,
		client_address: str | None = None,
		prerender_queue_timeout: float = 60.0,
		dev_strict_mode_detach_timeout: float = 0.0,
		disconnect_queue_timeout: float = 300.0,
		render_loop_limit: int = 50,
	) -> None:
		from pulse.channel import ChannelsManager
		from pulse.forms import FormRegistry

		self.id = id
		self.routes = routes
		self.views = {}
		self._views_by_path = {}
		self._server_address = server_address
		self._client_address = client_address
		self._send_message = None
		self._global_states = {}
		self._global_queue = []
		self.connected = False
		self.channels = ChannelsManager(self)
		self.forms = FormRegistry(self)
		self._pending_api = {}
		self._pending_js_results = {}
		self._ref_channel = None
		self._ref_channels_by_view = {}
		self._tasks = TaskRegistry(name=f"render:{id}")
		self._timers = TimerRegistry(tasks=self._tasks, name=f"render:{id}")
		self.query_store = QueryStore()
		self.prerender_queue_timeout = prerender_queue_timeout
		self.dev_strict_mode_detach_timeout = dev_strict_mode_detach_timeout
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
		for view_id in list(self.views.keys()):
			self.report_error(view_id, "effect", exc, details)

	# ---- Connection lifecycle ----

	def connect(self, send_message: Callable[[ServerMessage], Any]):
		"""WebSocket connected. Set sender, don't auto-flush (attach does that)."""
		self._send_message = send_message
		self.connected = True
		if self._global_queue:
			queued = self._global_queue
			self._global_queue = []
			for msg in queued:
				self.send(msg)

	def disconnect(self):
		"""WebSocket disconnected. Start queuing briefly before pausing."""
		self._send_message = None
		self.connected = False
		self.channels.disconnect_all()

		for view in self.views.values():
			if view.state == "active":
				view.start_pending(self.disconnect_queue_timeout)

	# ---- Message routing ----

	def send(self, message: ServerMessage):
		"""Route message based on the owning view's state."""
		# Forced navigation is global. View-bound navigation is dropped once its
		# origin view has been disposed or its URL has changed since.
		if message.get("type") == "navigate_to":
			source_view = message.get("sourceView")
			source_pathname = message.get("sourcePathname")
			if isinstance(source_view, str):
				view = self.views.get(source_view)
				if view is None:
					return
				if isinstance(source_pathname, str):
					with Untrack():
						if view.route.pathname != source_pathname:
							return
			if self._send_message:
				self._send_message(message)
			else:
				self._global_queue.append(message)
			return
		# Global messages (not view-specific) go directly if connected
		view_id = message.get("view")
		if view_id is None:
			if self._send_message:
				self._send_message(message)
			else:
				self._global_queue.append(message)
			return

		view = self.views.get(view_id)
		if not view:
			# Unknown view - send directly if connected (client discards stale ids)
			if self._send_message:
				self._send_message(message)
			return

		if self._send_message:
			view.deliver(message, self._send_message)
			return
		if view.state == "pending":
			view.deliver(message, lambda _: None)
		# idle: drop (effect should be paused anyway)

	def report_error(
		self,
		view_id: str | None,
		phase: ServerErrorPhase,
		exc: BaseException,
		details: dict[str, Any] | None = None,
	):
		message: ServerErrorMessage = {
			"type": "server_error",
			"error": {
				"message": str(exc),
				"stack": traceback.format_exc(),
				"phase": phase,
				"details": details or {},
			},
		}
		if view_id is not None:
			message["view"] = view_id
		self.send(message)
		logger.error(
			"Error reported for view %r during %s: %s\n%s",
			view_id,
			phase,
			exc,
			traceback.format_exc(),
		)

	# ---- Prerendering ----

	def prerender(
		self, paths: list[str], route_info: RouteInfo | None = None
	) -> dict[str, ServerInitMessage | ServerNavigateToMessage]:
		"""
		Synchronous render for SSR. Returns per-path init or navigate_to messages.
		- Creates views in PENDING state and starts queue
		"""
		normalized = [ensure_absolute_path(path) for path in paths]

		results: dict[str, ServerInitMessage | ServerNavigateToMessage] = {}

		for path in normalized:
			route = self.routes.find(path)
			info = route_info or route.default_route_info()
			view = self._views_by_path.get(path)

			if view is None:
				view = View(self, path, route, info)
				self.views[view.id] = view
				self._views_by_path[path] = view
			else:
				view.update_route(info)
				if route_info is not None and view.state == "active":
					view.start_pending(self.prerender_queue_timeout)

			if view.state != "active" and view.queue_timeout is None:
				view.start_pending(self.prerender_queue_timeout)
			message = self.render(view)

			results[path] = message
			if message["type"] == "navigate_to":
				self.dispose_view(view)
				continue

		return results

	# ---- Client lifecycle ----

	def attach(self, view_id: str, route_info: RouteInfo) -> bool:
		"""
		Client ready to receive updates for a view.
		- PENDING: flush queue, transition to ACTIVE
		- IDLE: request reload
		- ACTIVE: update route_info
		- Unknown view: request reload
		Returns True when callbacks can be accepted for this view.
		"""
		view = self.views.get(view_id)

		if view is None or view.state == "idle":
			# Initial render must come from prerender
			self.send({"type": "reload"})
			return False

		# Update route info for active and pending views
		view.update_route(route_info)
		if view.state == "pending" and self._send_message:
			view.activate(self._send_message)
		return view.state == "active"

	def resume(
		self,
		resume_id: str,
		views: list[ClientResumeView],
		channels: list[ClientResumeChannel],
	) -> bool:
		accepted_views: list[ServerResumeView] = []

		for declared in views:
			view_id = declared["view"]
			view = self.views.get(view_id)
			if view is None or view.state in ("idle", "closed"):
				self.send(
					ServerResumeMessage(
						type="server_resume",
						resumeId=resume_id,
						status="reload",
					)
				)
				return False
			view.update_route(declared["routeInfo"])
			if view.state == "pending" and self._send_message:
				view.activate(self._send_message)
			if view.state != "active":
				self.send(
					ServerResumeMessage(
						type="server_resume",
						resumeId=resume_id,
						status="reload",
					)
				)
				return False
			resumed_view: ServerResumeView = {"view": view_id}
			if attach_id := declared.get("attachId"):
				resumed_view["attachId"] = attach_id
			accepted_views.append(resumed_view)

		accepted_channels: list[ServerResumeChannel] = []
		for channel in channels:
			channel_id = str(channel.get("channel", ""))
			view_id = str(channel.get("view", ""))
			# resume_client_channel validates view-bound channels against their
			# owning view; channels without a view binding resume freely.
			if self.channels.resume_client_channel(channel_id, view_id):
				accepted_channels.append({"channel": channel_id, "view": view_id})

		self.send(
			ServerResumeMessage(
				type="server_resume",
				resumeId=resume_id,
				status="ok",
				views=accepted_views,
				channels=accepted_channels,
			)
		)
		return True

	def update_route(self, view_id: str, route_info: RouteInfo):
		"""Update routing state (query params, etc.) for an attached view."""
		view = self.views.get(view_id)
		if view is None:
			# No-op when the view does not exist yet.
			# Route updates may arrive before prerender; prerender creates the view
			# with the authoritative RouteInfo, so replaying/stashing is unnecessary.
			return
		try:
			view.update_route(route_info)
			if view.state == "pending" and self._send_message:
				view.activate(self._send_message)
		except Exception as e:
			self.report_error(view.id, "navigate", e)

	def dispose_view(self, view: View) -> None:
		current = self.views.get(view.id)
		if current is not view:
			return
		try:
			self.channels.remove_view(view.id)
			self.views.pop(view.id, None)
			if self._views_by_path.get(view.route_path) is view:
				self._views_by_path.pop(view.route_path, None)
			self._ref_channels_by_view.pop(view.id, None)
			view.dispose()
		except Exception as e:
			self.report_error(view.id, "unmount", e)

	def detach(self, view_id: str):
		"""Client view unmounted. Dispose immediately outside dev StrictMode replay."""
		view = self.views.get(view_id)
		if not view:
			return
		if self.dev_strict_mode_detach_timeout > 0:
			# React StrictMode in development intentionally replays mount effects as
			# attach -> detach -> attach without another prerender. Keep the view
			# alive for a very short dev-only window so the replayed attach can
			# cancel the disposal. The view keeps its id: the replayed attach is
			# the same logical view.
			view.start_pending(self.dev_strict_mode_detach_timeout, action="dispose")
			return
		self.dispose_view(view)

	# ---- Rendering ----

	def _check_render_loop(self, view: View) -> None:
		batch_id = REACTIVE_CONTEXT.get().batch.flush_id
		if view.render_batch_id == batch_id:
			view.render_batch_renders += 1
		else:
			view.render_batch_id = batch_id
			view.render_batch_renders = 1
		if view.render_batch_renders > self.render_loop_limit:
			view.tree.pause_effects()
			raise RenderLoopError(view.route_path, view.render_batch_renders, batch_id)

	def _render_with_interrupts(
		self,
		view: View,
		*,
		session: Any | None = None,
		render_fn: Callable[[], T_Render],
	) -> T_Render | ServerNavigateToMessage:
		ctx = PulseContext.get()
		render_session = ctx.session if session is None else session
		with Untrack():
			source_pathname = view.route.pathname
		with PulseContext.update(
			session=render_session,
			render=self,
			route=view.route,
			view=view,
			source_pathname=source_pathname,
		):
			try:
				self._check_render_loop(view)
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
		self, view: View, *, session: Any | None = None
	) -> ServerInitMessage | ServerNavigateToMessage:
		def _render() -> ServerInitMessage:
			vdom = view.tree.render()
			view.initialized = True
			return ServerInitMessage(
				type="vdom_init",
				view=view.id,
				routePath=view.route_path,
				vdom=vdom,
			)

		return self._render_with_interrupts(view, session=session, render_fn=_render)

	def render_component_pass(
		self, view: View, runtime: Any
	) -> ServerUpdateMessage | ServerNavigateToMessage | None:
		"""Re-render one component subtree within the view's Pulse context."""

		def _pass() -> ServerUpdateMessage | None:
			if not view.initialized:
				raise RuntimeError(
					f"component render before init for {view.route_path!r}"
				)
			ops = view.tree.run_component_pass(runtime)
			if ops:
				return ServerUpdateMessage(type="vdom_update", view=view.id, ops=ops)
			return None

		return self._render_with_interrupts(view, session=view.session, render_fn=_pass)

	# ---- Helpers ----

	def close(self):
		# Close all pending timers at the start, to avoid anything firing while we clean up
		self._timers.cancel_all()
		self.forms.dispose()
		self._tasks.cancel_all()
		for view in list(self.views.values()):
			self.dispose_view(view)
		self.views.clear()
		self._views_by_path.clear()
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
		self._ref_channel = None
		self._ref_channels_by_view.clear()
		# Close any timer that may have been scheduled during cleanup (ex: query GC)
		self._timers.cancel_all()
		self._global_queue = []
		self._send_message = None
		self.connected = False

	def get_view(self, view_id: str) -> View:
		view = self.views.get(view_id)
		if not view:
			raise ValueError(f"No view with id '{view_id}'")
		return view

	def view_for_path(self, path: str) -> View:
		"""Look up the view rendering the given route pattern path."""
		path = ensure_absolute_path(path)
		view = self._views_by_path.get(path)
		if not view:
			raise ValueError(f"No view for route '{path}'")
		return view

	def get_global_state(self, key: str, factory: Callable[[], Any]) -> Any:
		"""Return a per-session singleton for the provided key."""
		inst = self._global_states.get(key)
		if inst is None:
			inst = factory()
			self._global_states[key] = inst
		return inst

	def get_ref_channel(self) -> Channel:
		ctx = PulseContext.get()
		if ctx.view is None:
			if self._ref_channel is not None and not self._ref_channel.closed:
				return self._ref_channel
			self._ref_channel = self.channels.create(bind_view=False)
			return self._ref_channel

		view_id = ctx.view.id
		channel = self._ref_channels_by_view.get(view_id)
		if channel is not None and channel.closed:
			self._ref_channels_by_view.pop(view_id, None)
			channel = None
		if channel is None:
			channel = self.channels.create(bind_view=True)
			self._ref_channels_by_view[view_id] = channel
		return channel

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

	def execute_callback(
		self, view_id: str, key: str, args: list[Any] | tuple[Any, ...]
	):
		view = self.views.get(view_id)
		if view is None or view.state == "closed":
			logger.warning("Dropping callback %r for missing view %r", key, view_id)
			return
		cb = view.tree.callbacks.get(key)
		if cb is None:
			logger.warning(
				"Dropping stale callback %r for view %r", key, view.route_path
			)
			return

		def report(e: BaseException, is_async: bool = False):
			self.report_error(
				view.id, "callback", e, {"callback": key, "async": is_async}
			)

		try:
			with Untrack():
				source_pathname = view.route.pathname
			with PulseContext.update(
				render=self,
				route=view.route,
				view=view,
				source_pathname=source_pathname,
			):
				res = cb.fn(*(args if cb.accepts_varargs else args[: cb.n_args]))
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
		if ctx.view is None:
			raise RuntimeError(
				"run_js() requires an active view context (component render, callback, or effect)"
			)
		exec_id = next_id()

		self.send(
			ServerJsExecMessage(
				type="js_exec",
				view=ctx.view.id,
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
