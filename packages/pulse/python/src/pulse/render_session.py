import asyncio
import bisect
import heapq
import logging
import time
import traceback
import uuid
from asyncio import iscoroutine
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from pulse.channel import Channel
from pulse.context import PulseContext
from pulse.hooks.runtime import NotFoundInterrupt, RedirectInterrupt
from pulse.messages import (
	RouteOrigin,
	ServerApiCallMessage,
	ServerAttachAckMessage,
	ServerErrorMessage,
	ServerErrorPhase,
	ServerInitMessage,
	ServerJsExecMessage,
	ServerMessage,
	ServerNavigateToMessage,
	ServerUpdateMessage,
	ViewSnapshot,
)
from pulse.queries.store import QueryStore
from pulse.reactive import REACTIVE_CONTEXT, Effect, flush_effects
from pulse.renderer import Callback, Callbacks, RenderTree
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


MountState = Literal["pending", "active", "suspended", "closed"]
T_Render = TypeVar("T_Render")
CALLBACK_HISTORY_VERSIONS = 20_000
CALLBACK_HISTORY_REVISIONS = 100_000
CALLBACK_UNAVAILABLE = object()


@dataclass(slots=True)
class CallbackVersion:
	revision: int
	callback: Callback | None


@dataclass(slots=True)
class CallbackRevision:
	revision: int
	superseded_at: float | None = None


class CallbackHistory:
	retention_seconds: float
	current: Callbacks
	revisions: deque[CallbackRevision]
	versions: dict[str, list[CallbackVersion]]
	next_changes: list[tuple[int, str]]
	version_count: int

	def __init__(self, retention_seconds: float) -> None:
		self.retention_seconds = retention_seconds
		self.current = {}
		self.revisions = deque()
		self.versions = {}
		self.next_changes = []
		self.version_count = 0

	@property
	def oldest_revision(self) -> int | None:
		return self.revisions[0].revision if self.revisions else None

	@property
	def latest_revision(self) -> int | None:
		return self.revisions[-1].revision if self.revisions else None

	def clear(self) -> None:
		self.current.clear()
		self.revisions.clear()
		self.versions.clear()
		self.next_changes.clear()
		self.version_count = 0

	def record(self, revision: int, callbacks: Callbacks, *, now: float) -> None:
		latest = self.latest_revision
		if latest is not None and revision != latest + 1:
			raise RuntimeError(
				f"Callback revisions must be sequential: got {revision} after {latest}"
			)
		if self.revisions:
			self.revisions[-1].superseded_at = now

		for key in self.current.keys() | callbacks.keys():
			previous = self.current.get(key)
			current = callbacks.get(key)
			if self._same_callback(previous, current):
				continue
			versions = self.versions.setdefault(key, [])
			versions.append(CallbackVersion(revision, current))
			if len(versions) == 2:
				heapq.heappush(self.next_changes, (revision, key))
			self.version_count += 1

		self.current = dict(callbacks)
		self.revisions.append(CallbackRevision(revision))
		self.prune(now=now)

	def lookup(
		self, revision: int, key: str, *, now: float
	) -> Callback | object | None:
		self.prune(now=now)
		oldest = self.oldest_revision
		latest = self.latest_revision
		if oldest is None or revision < oldest or latest is None or revision > latest:
			return CALLBACK_UNAVAILABLE
		versions = self.versions.get(key)
		if not versions:
			return None
		index = bisect.bisect_right(
			versions, revision, key=lambda version: version.revision
		)
		if index == 0:
			return None
		return versions[index - 1].callback

	def prune(self, *, now: float) -> None:
		while len(self.revisions) > 1:
			oldest = self.revisions[0]
			assert oldest.superseded_at is not None
			within_ttl = now - oldest.superseded_at < self.retention_seconds
			within_version_limit = self.version_count <= CALLBACK_HISTORY_VERSIONS
			within_revision_limit = len(self.revisions) <= CALLBACK_HISTORY_REVISIONS
			if within_ttl and within_version_limit and within_revision_limit:
				break
			self.revisions.popleft()
			floor = self.revisions[0].revision
			self._prune_versions(floor)

	def _prune_versions(self, floor: int) -> None:
		while self.next_changes and self.next_changes[0][0] <= floor:
			revision, key = heapq.heappop(self.next_changes)
			versions = self.versions.get(key)
			if not versions or len(versions) < 2 or versions[1].revision != revision:
				continue
			self._prune_key(key, floor)
			versions = self.versions.get(key)
			if versions and len(versions) >= 2:
				heapq.heappush(self.next_changes, (versions[1].revision, key))

	def _prune_key(self, key: str, floor: int) -> None:
		versions = self.versions.get(key)
		if not versions:
			return
		index = (
			bisect.bisect_right(versions, floor, key=lambda version: version.revision)
			- 1
		)
		if index < 0:
			return
		keep_from = index if versions[index].callback is not None else index + 1
		if keep_from:
			del versions[:keep_from]
			self.version_count -= keep_from
		if not versions:
			self.versions.pop(key, None)

	@staticmethod
	def _same_callback(left: Callback | None, right: Callback | None) -> bool:
		if left is None or right is None:
			return left is right
		return (
			left.fn is right.fn
			and left.n_args == right.n_args
			and left.accepts_varargs == right.accepts_varargs
		)


class RouteMount:
	render: "RenderSession"
	path: str
	route: RouteContext
	tree: RenderTree
	effect: Effect | None
	_pulse_ctx: PulseContext | None
	initialized: bool
	state: MountState
	ever_active: bool
	dispose_on_timeout: bool
	queue: list[ServerMessage] | None
	queue_timeout: TimerHandleLike | None
	snapshot_required: bool
	view_id: str
	revision: int
	instance_id: str | None
	callback_history: CallbackHistory
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
		self.route = RouteContext(route_info, route, render, self.path)
		self.effect = None
		self._pulse_ctx = None
		self.tree = RenderTree(route.render())
		self.initialized = False
		self.state = "pending"
		self.ever_active = False
		self.dispose_on_timeout = False
		self.queue = []
		self.queue_timeout = None
		self.snapshot_required = False
		self.view_id = uuid.uuid4().hex
		self.revision = -1
		self.instance_id = None
		self.callback_history = CallbackHistory(render.disconnect_queue_timeout)
		self.render_batch_id = -1
		self.render_batch_renders = 0

	def update_route(self, route_info: RouteInfo) -> None:
		self.route.update(route_info)

	def origin(self) -> RouteOrigin:
		return {"viewId": self.view_id, "pathname": self.route.pathname}

	def _cancel_pending_timeout(self) -> None:
		if self.queue_timeout is not None:
			self.queue_timeout.cancel()
			self.render.discard_timer(self.queue_timeout)
			self.queue_timeout = None

	def _on_pending_timeout(self) -> None:
		if self.state != "pending":
			return
		# Mounts the client never attached to (e.g. crawler prerenders) and
		# explicit detaches are garbage; attached mounts suspend so the user
		# can resume with their state intact.
		if self.dispose_on_timeout or not self.ever_active:
			self.render.dispose_mount(self.path, self)
			return
		self.suspend()

	def start_pending(self, timeout: float, *, dispose: bool = False) -> None:
		dispose = dispose or (self.state == "pending" and self.dispose_on_timeout)
		self._cancel_pending_timeout()
		if self.state != "pending":
			if self.state == "suspended" and self.effect:
				self.effect.resume()
			self.state = "pending"
			self.queue = []
			self.snapshot_required = False
		self.dispose_on_timeout = dispose
		self.queue_timeout = self.render.schedule_later(
			timeout, self._on_pending_timeout
		)

	def activate(
		self, send_message: Callable[[ServerMessage], Any], *, flush: bool = True
	) -> None:
		if self.state != "pending":
			return
		self._cancel_pending_timeout()
		if flush and self.queue:
			for msg in self.queue:
				send_message(msg)
		self.queue = None
		self.snapshot_required = False
		self.state = "active"
		self.ever_active = True
		self.dispose_on_timeout = False

	def suspend(self) -> None:
		"""Pause rendering but keep the mounted tree and hook state for resume."""
		if self.state != "pending":
			return
		self.state = "suspended"
		self.queue = None
		self.snapshot_required = False
		self._cancel_pending_timeout()
		if self.effect:
			self.effect.pause()

	def deliver(
		self, message: ServerMessage, send_message: Callable[[ServerMessage], Any]
	):
		if self.state == "pending":
			if self.queue is None:
				raise RuntimeError(f"Pending mount missing queue for {self.path!r}")
			if self.snapshot_required:
				return
			# Leave one sender-queue slot for the attach acknowledgement.
			if len(self.queue) >= self.render.pending_message_limit - 1:
				self.queue.clear()
				self.snapshot_required = True
				return
			self.queue.append(message)
			return
		if self.state == "active":
			send_message(message)
			return
		if self.state == "closed":
			raise RuntimeError(f"Message sent to closed mount {self.path!r}")
		# suspended: drop; the client gets a fresh init on resume

	def can_replay_from(self, revision: int) -> bool:
		if self.snapshot_required:
			return False
		current = revision
		for message in self.queue or []:
			if message["type"] != "vdom_update":
				continue
			if message["viewId"] != self.view_id or message["baseRevision"] != current:
				return False
			current = message["revision"]
		return current == self.revision

	def record_callbacks(self) -> None:
		self.callback_history.record(
			self.revision, self.tree.callbacks, now=time.monotonic()
		)

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
		self.snapshot_required = False
		self.callback_history.clear()
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
	dev_strict_mode_detach_timeout: float
	disconnect_queue_timeout: float
	pending_message_limit: int
	render_loop_limit: int
	_server_address: str | None
	_client_address: str | None
	_send_message: Callable[[ServerMessage], Any] | None
	_pending_api: dict[str, asyncio.Future[dict[str, Any]]]
	_pending_js_results: dict[str, tuple[str, asyncio.Future[Any]]]
	_ref_channel: Channel | None
	_ref_channels_by_route: dict[str, Channel]
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
		pending_message_limit: int = 100,
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
		self._global_queue = []
		self.connected = False
		self.channels = ChannelsManager(self)
		self.forms = FormRegistry(self)
		self._pending_api = {}
		self._pending_js_results = {}
		self._ref_channel = None
		self._ref_channels_by_route = {}
		self._tasks = TaskRegistry(name=f"render:{id}")
		self._timers = TimerRegistry(tasks=self._tasks, name=f"render:{id}")
		self.query_store = QueryStore()
		self.prerender_queue_timeout = prerender_queue_timeout
		self.dev_strict_mode_detach_timeout = dev_strict_mode_detach_timeout
		self.disconnect_queue_timeout = disconnect_queue_timeout
		self.pending_message_limit = pending_message_limit
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

	def connect(
		self, send_message: Callable[[ServerMessage], Any], *, replacing: bool = False
	):
		"""WebSocket connected. Set sender, don't auto-flush (attach does that)."""
		self._send_message = send_message
		self.connected = True
		if self._global_queue:
			queued = self._global_queue
			self._global_queue = []
			for msg in queued:
				self.send(msg)
		# Restart query intervals and refetch stale data (no-op on first connect).
		# Establishes render context here (so resume fetch-tasks register on this
		# render); the session is inherited from the caller's context, which must
		# wrap connect() so reconnect fetches match initial fetches.
		with PulseContext.update(render=self):
			if replacing:
				self.query_store.reconnect_all()
			else:
				self.query_store.resume_all()

	def disconnect(self):
		"""WebSocket disconnected. Queue briefly, then suspend mounts on timeout."""
		self._send_message = None
		self.connected = False
		# Pause query interval refetching while nobody is watching
		self.query_store.suspend_all()

		for mount in self.route_mounts.values():
			if mount.state == "active":
				mount.start_pending(self.disconnect_queue_timeout)

	# ---- Message routing ----

	def send(self, message: ServerMessage):
		"""Route message based on mount state."""
		# Forced navigation is global. Origin-bound navigation is dropped once
		# its source view or pathname is no longer current.
		if message.get("type") == "navigate_to":
			origin = message.get("origin")
			if origin is not None:
				mount = self._get_mount_by_view_id(origin["viewId"])
				if mount is None or mount.route.pathname != origin["pathname"]:
					return
			if self._send_message:
				self._send_message(message)
			else:
				self._global_queue.append(message)
			return
		# Global messages (not path-specific) go directly if connected
		path = message.get("path")
		if path is None:
			if self._send_message:
				self._send_message(message)
			else:
				self._global_queue.append(message)
			return

		# Normalize path for lookup
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			# Unknown path - send directly if connected (for js_exec, etc.)
			if self._send_message:
				self._send_message(message)
			return
		view_id = message.get("viewId")
		if isinstance(view_id, str) and view_id != mount.view_id:
			return

		if self._send_message:
			mount.deliver(message, self._send_message)
			return
		if mount.state == "pending":
			mount.deliver(message, lambda _: None)

	def report_error(
		self,
		path: str,
		phase: ServerErrorPhase,
		exc: BaseException,
		details: dict[str, Any] | None = None,
	):
		# Format from the exception object, not the ambient sys.exc_info(): this
		# is also called outside an `except` block (e.g. a deferred connect error),
		# where traceback.format_exc() would yield "NoneType: None".
		stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
		message = ServerErrorMessage(
			type="server_error",
			path=path,
			error={
				"message": str(exc),
				"stack": stack,
				"phase": phase,
				"details": details or {},
			},
		)
		mount = self.route_mounts.get(ensure_absolute_path(path))
		if mount is not None:
			message["viewId"] = mount.view_id
		self.send(message)
		logger.error(
			"Error reported for path %r during %s: %s\n%s",
			path,
			phase,
			exc,
			stack,
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

		results: dict[str, ServerInitMessage | ServerNavigateToMessage] = {}

		for path in normalized:
			route = self.routes.find(path)
			info = route_info or route.default_route_info()
			mount = self.route_mounts.get(path)

			if mount is None:
				mount = RouteMount(self, path, route, info)
				self.route_mounts[path] = mount
				mount.ensure_effect(lazy=True, flush=False)
			else:
				mount.update_route(info)
				if mount.effect is None:
					mount.ensure_effect(lazy=True, flush=False)
				if route_info is not None and mount.state == "active":
					mount.start_pending(self.prerender_queue_timeout)

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

	def attach(
		self,
		path: str,
		route_info: RouteInfo,
		view_id: str,
		revision: int,
		attach_id: str,
		instance_id: str,
	) -> ServerAttachAckMessage | None:
		"""
		Client ready to receive updates for path.
		- PENDING: replay a contiguous queue or send a snapshot
		- SUSPENDED: re-render and include a snapshot
		- ACTIVE: acknowledge matching state or include a snapshot
		- No mount: request reload
		"""
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)

		if mount is None:
			# Initial render must come from prerender
			self.send({"type": "reload"})
			return None
		if mount.view_id != view_id:
			self.send({"type": "reload"})
			return None

		mount.update_route(route_info)
		if mount.instance_id is None:
			mount.instance_id = instance_id
		elif mount.instance_id != instance_id:
			self.send({"type": "reload"})
			return None
		ack = ServerAttachAckMessage(
			type="attach_ack",
			path=path,
			attachId=attach_id,
			viewId=mount.view_id,
			revision=mount.revision,
		)
		if mount.state == "pending" and mount.can_replay_from(revision):
			assert self._send_message is not None
			mount.activate(self._send_message)
			ack["revision"] = mount.revision
			return ack
		if mount.state == "active" and revision == mount.revision:
			return ack

		snapshot = self._snapshot_mount(mount, path)
		if snapshot is None:
			return None
		ack["viewId"] = snapshot["viewId"]
		ack["revision"] = snapshot["revision"]
		ack["snapshot"] = snapshot
		return ack

	def _snapshot_mount(self, mount: RouteMount, path: str) -> ViewSnapshot | None:
		assert mount.effect is not None
		if mount.state == "suspended":
			mount.start_pending(self.disconnect_queue_timeout)
		with mount.effect.capture_deps(update_deps=True):
			message = self.render(mount, path)
		if message["type"] == "navigate_to":
			self.send(message)
			self.dispose_mount(path, mount)
			return None
		if mount.state == "pending":
			assert self._send_message is not None
			mount.activate(self._send_message, flush=False)
		return {
			"viewId": message["viewId"],
			"revision": message["revision"],
			"vdom": message["vdom"],
		}

	def update_route(
		self, path: str, route_info: RouteInfo, view_id: str, revision: int
	) -> None:
		"""Update routing state (query params, etc.) for attached path."""
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if mount is None or mount.view_id != view_id:
			# No-op when mount does not exist yet.
			# Route updates may arrive before prerender; prerender creates the mount with
			# the authoritative RouteInfo, so replaying/stashing is unnecessary.
			return
		try:
			mount.update_route(route_info)
			if mount.state == "pending" and self._send_message:
				if mount.can_replay_from(revision):
					mount.activate(self._send_message)
				else:
					self._send_message(
						{"type": "resync_view", "path": path, "viewId": view_id}
					)
			elif mount.state == "active" and revision != mount.revision:
				self.send({"type": "resync_view", "path": path, "viewId": view_id})
		except Exception as e:
			self.report_error(path, "navigate", e)

	def dispose_mount(self, path: str, mount: RouteMount) -> None:
		current = self.route_mounts.get(path)
		if current is not mount:
			return
		self.route_mounts.pop(path, None)
		self._ref_channels_by_route.pop(path, None)
		try:
			mount.dispose()
		except Exception as e:
			self.report_error(path, "unmount", e)
		finally:
			self.channels.remove_route(path)

	def detach(self, path: str, view_id: str, instance_id: str) -> bool:
		"""Client route unmounted. Dispose immediately outside dev StrictMode replay."""
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if (
			mount is None
			or mount.view_id != view_id
			or mount.instance_id != instance_id
		):
			return False
		if self.dev_strict_mode_detach_timeout > 0:
			# React StrictMode in development intentionally replays mount effects as
			# attach -> detach -> attach without another prerender. Keep the mount for
			# a very short dev-only window so that synthetic cleanup can be cancelled
			# by the replayed attach. This remains the same logical view.
			mount.start_pending(self.dev_strict_mode_detach_timeout, dispose=True)
			return True
		self.dispose_mount(path, mount)
		return True

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
			session=render_session,
			render=self,
			route=mount.route,
			origin=mount.origin(),
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
					origin=mount.origin(),
				)
			except NotFoundInterrupt:
				ctx = PulseContext.get()
				return ServerNavigateToMessage(
					type="navigate_to",
					path=ctx.app.not_found,
					replace=True,
					hard=False,
					origin=mount.origin(),
				)

	def render(
		self, mount: RouteMount, path: str, *, session: Any | None = None
	) -> ServerInitMessage | ServerNavigateToMessage:
		def _render() -> ServerInitMessage:
			vdom = mount.tree.render()
			mount.initialized = True
			mount.revision += 1
			mount.record_callbacks()
			return ServerInitMessage(
				type="vdom_init",
				path=path,
				viewId=mount.view_id,
				revision=mount.revision,
				vdom=vdom,
			)

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
			base_revision = mount.revision
			mount.revision += 1
			mount.record_callbacks()
			return ServerUpdateMessage(
				type="vdom_update",
				path=path,
				viewId=mount.view_id,
				baseRevision=base_revision,
				revision=mount.revision,
				ops=ops,
			)

		return self._render_with_interrupts(
			mount, path, session=session, render_fn=_rerender
		)

	# ---- Helpers ----

	def close(self):
		# Close all pending timers at the start, to avoid anything firing while we clean up
		self._timers.cancel_all()
		self.forms.dispose()
		self._tasks.cancel_all()
		for path, mount in list(self.route_mounts.items()):
			self.dispose_mount(path, mount)
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
		for _, fut in self._pending_js_results.values():
			if not fut.done():
				fut.cancel()
		self._pending_js_results.clear()
		self._ref_channel = None
		self._ref_channels_by_route.clear()
		# Close any timer that may have been scheduled during cleanup (ex: query GC)
		self._timers.cancel_all()
		self._global_queue = []
		self._send_message = None
		self.connected = False

	def get_route_mount(self, path: str) -> RouteMount:
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if not mount:
			raise ValueError(f"No active route for '{path}'")
		return mount

	def _get_mount_by_view_id(self, view_id: str) -> RouteMount | None:
		return next(
			(mount for mount in self.route_mounts.values() if mount.view_id == view_id),
			None,
		)

	def get_global_state(self, key: str, factory: Callable[[], Any]) -> Any:
		"""Return a per-session singleton for the provided key."""
		inst = self._global_states.get(key)
		if inst is None:
			inst = factory()
			self._global_states[key] = inst
		return inst

	def get_ref_channel(self) -> Channel:
		ctx = PulseContext.get()
		if ctx.route is None:
			if self._ref_channel is not None and not self._ref_channel.closed:
				return self._ref_channel
			self._ref_channel = self.channels.create(bind_route=False)
			return self._ref_channel

		route_path = ctx.route.route_path
		channel = self._ref_channels_by_route.get(route_path)
		if channel is not None and channel.closed:
			self._ref_channels_by_route.pop(route_path, None)
			channel = None
		if channel is None:
			channel = self.channels.create(bind_route=True)
			self._ref_channels_by_route[route_path] = channel
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
		self,
		path: str,
		view_id: str,
		revision: int,
		key: str,
		args: list[Any] | tuple[Any, ...],
	) -> None:
		path = ensure_absolute_path(path)
		mount = self.route_mounts.get(path)
		if mount is None or mount.state == "closed" or mount.view_id != view_id:
			logger.warning("Dropping callback %r for missing route %r", key, path)
			return
		callback = mount.callback_history.lookup(revision, key, now=time.monotonic())
		if callback is CALLBACK_UNAVAILABLE:
			logger.warning(
				"Dropping callback %r for unavailable revision %s on route %r",
				key,
				revision,
				path,
			)
			self.send({"type": "resync_view", "path": path, "viewId": view_id})
			return
		if callback is None:
			logger.warning("Dropping stale callback %r for route %r", key, path)
			self.send({"type": "resync_view", "path": path, "viewId": view_id})
			return
		assert isinstance(callback, Callback)
		cb = callback

		def report(e: BaseException, is_async: bool = False):
			self.report_error(path, "callback", e, {"callback": key, "async": is_async})

		try:
			with PulseContext.update(
				render=self,
				route=mount.route,
				origin=mount.origin(),
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
		if ctx.origin is None:
			raise RuntimeError("run_js() requires an active route view")
		exec_id = next_id()

		# Get route pattern path (e.g., "/users/:id") not pathname (e.g., "/users/123")
		# This must match the path used to key views on the client side
		path = ctx.route.pulse_route.unique_path() if ctx.route else "/"

		self.send(
			ServerJsExecMessage(
				type="js_exec",
				path=path,
				viewId=ctx.origin["viewId"],
				id=exec_id,
				expr=expr.render(),
			)
		)

		if result:
			loop = asyncio.get_running_loop()
			future: asyncio.Future[object] = loop.create_future()
			self._pending_js_results[exec_id] = (ctx.origin["viewId"], future)

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
		pending = self._pending_js_results.get(exec_id)
		if pending is None:
			return
		view_id, fut = pending
		if data.get("viewId") != view_id or fut.done():
			return
		self._pending_js_results.pop(exec_id, None)
		error = data.get("error")
		if error is not None:
			fut.set_exception(JsExecError(error))
		else:
			fut.set_result(data.get("result"))
